# coding: utf-8
import pytest

from _pydevd_bundle._debug_adapter import pydevd_schema, pydevd_base_schema
from _pydevd_bundle._debug_adapter.pydevd_base_schema import from_json
from tests_python.debugger_unittest import IS_JYTHON, REASON_STEP_INTO, REASON_STEP_OVER, \
    REASON_CAUGHT_EXCEPTION, REASON_THREAD_SUSPEND, REASON_STEP_RETURN, IS_APPVEYOR, overrides, \
    REASON_UNCAUGHT_EXCEPTION
from _pydevd_bundle._debug_adapter.pydevd_schema import ThreadEvent, ModuleEvent, OutputEvent, \
    ExceptionOptions
from tests_python import debugger_unittest
import json
from collections import namedtuple
from _pydevd_bundle.pydevd_constants import int_types
from tests_python.debug_constants import *  # noqa
import time

pytest_plugins = [
    str('tests_python.debugger_fixtures'),
]

_JsonHit = namedtuple('_JsonHit', 'frameId')

# Note: in reality must be < int32, but as it's created sequentially this should be
# a reasonable number for tests.
MAX_EXPECTED_ID = 10000


class JsonFacade(object):

    def __init__(self, writer):
        self.writer = writer

    def wait_for_json_message(self, expected_class, accept_message=lambda obj:True):

        def accept_json_message(msg):
            if msg.startswith('{'):
                decoded_msg = from_json(msg)
                if isinstance(decoded_msg, expected_class):
                    if accept_message(decoded_msg):
                        return True
            return False

        msg = self.writer.wait_for_message(accept_json_message, unquote_msg=False, expect_xml=False)
        return from_json(msg)

    def wait_for_response(self, request):
        response_class = pydevd_base_schema.get_response_class(request)

        def accept_message(response):
            if isinstance(request, dict):
                if response.request_seq == request['seq']:
                    return True
            else:
                if response.request_seq == request.seq:
                    return True
            return False

        return self.wait_for_json_message(response_class, accept_message)

    def write_request(self, request):
        seq = self.writer.next_seq()
        if isinstance(request, dict):
            request['seq'] = seq
            self.writer.write_with_content_len(json.dumps(request))
        else:
            request.seq = seq
            self.writer.write_with_content_len(request.to_json())
        return request

    def write_make_initial_run(self):
        configuration_done_request = self.write_request(pydevd_schema.ConfigurationDoneRequest())
        return self.wait_for_response(configuration_done_request)

    def write_list_threads(self):
        return self.wait_for_response(self.write_request(pydevd_schema.ThreadsRequest()))

    def write_set_breakpoints(self, lines, filename=None, line_to_info=None):
        '''
        Adds a breakpoint.
        '''
        if isinstance(lines, int):
            lines = [lines]

        if line_to_info is None:
            line_to_info = {}

        if filename is None:
            filename = self.writer.get_main_filename()

        source = pydevd_schema.Source(path=filename)
        breakpoints = []
        for line in lines:
            condition = None
            hit_condition = None
            log_message = None

            if line in line_to_info:
                line_info = line_to_info.get(line)
                condition = line_info.get('condition')
                hit_condition = line_info.get('hit_condition')
                log_message = line_info.get('log_message')

            breakpoints.append(pydevd_schema.SourceBreakpoint(
                line, condition=condition, hitCondition=hit_condition, logMessage=log_message).to_dict())

        arguments = pydevd_schema.SetBreakpointsArguments(source, breakpoints)
        request = pydevd_schema.SetBreakpointsRequest(arguments)

        # : :type response: SetBreakpointsResponse
        response = self.wait_for_response(self.write_request(request))
        body = response.body

        # : :type body: SetBreakpointsResponseBody
        assert len(body.breakpoints) == len(lines)
        lines_in_response = [b['line'] for b in body.breakpoints]
        assert set(lines_in_response) == set(lines)

    def write_set_exception_breakpoints(self, filters=None, exception_options=None):
        '''
        :param list(str) filters:
            A list with 'raised' or 'uncaught' entries.

        :param list(ExceptionOptions) exception_options:

        '''
        filters = filters or []
        assert set(filters).issubset(set(('raised', 'uncaught')))

        exception_options = exception_options or []
        exception_options = [exception_option.to_dict() for exception_option in exception_options]

        arguments = pydevd_schema.SetExceptionBreakpointsArguments(filters, exception_options)
        request = pydevd_schema.SetExceptionBreakpointsRequest(arguments)
        # : :type response: SetExceptionBreakpointsResponse
        response = self.wait_for_response(self.write_request(request))
        assert response.success

    def write_launch(self, **arguments):
        arguments['noDebug'] = False
        request = {'type': 'request', 'command': 'launch', 'arguments': arguments, 'seq':-1}
        self.wait_for_response(self.write_request(request))

    def write_disconnect(self):
        arguments = pydevd_schema.DisconnectArguments(terminateDebuggee=False)
        request = pydevd_schema.DisconnectRequest(arguments)
        self.wait_for_response(self.write_request(request))

    def get_stack_as_json_hit(self, thread_id):
        stack_trace_request = self.write_request(
            pydevd_schema.StackTraceRequest(pydevd_schema.StackTraceArguments(threadId=thread_id)))

        # : :type stack_trace_response: StackTraceResponse
        # : :type stack_trace_response_body: StackTraceResponseBody
        # : :type stack_frame: StackFrame
        stack_trace_response = self.wait_for_response(stack_trace_request)
        stack_trace_response_body = stack_trace_response.body
        assert len(stack_trace_response_body.stackFrames) > 0

        for stack_frame in stack_trace_response_body.stackFrames:
            assert stack_frame['id'] < MAX_EXPECTED_ID

        stack_frame = next(iter(stack_trace_response_body.stackFrames))

        return _JsonHit(frameId=stack_frame['id'])

    def get_variables_response(self, variables_reference):
        assert variables_reference < MAX_EXPECTED_ID
        variables_request = self.write_request(
            pydevd_schema.VariablesRequest(pydevd_schema.VariablesArguments(variables_reference)))
        variables_response = self.wait_for_response(variables_request)
        return variables_response

    def filter_return_variables(self, variables):
        ret = []
        for variable in variables:
            if variable['name'].startswith('(return)'):
                ret.append(variable)
        return ret

    def pop_variables_reference(self, lst):
        '''
        Modifies dicts in-place to remove the variablesReference and returns those (in the same order
        in which they were received).
        '''
        references = []
        for dct in lst:
            reference = dct.pop('variablesReference', None)
            if reference is not None:
                assert isinstance(reference, int_types)
                assert reference < MAX_EXPECTED_ID
            references.append(reference)
        return references


def test_case_json_logpoints(case_setup):
    with case_setup.test_file('_debugger_case_change_breaks.py') as writer:
        json_facade = JsonFacade(writer)

        writer.write_set_protocol('http_json')
        json_facade.write_launch()
        break_2 = writer.get_line_index_with_content('break 2')
        break_3 = writer.get_line_index_with_content('break 3')
        json_facade.write_set_breakpoints(
            [break_2, break_3],
            line_to_info={
                break_2: {'log_message': 'var {repr("_a")} is {_a}'}
        })
        json_facade.write_make_initial_run()

        # Should only print, not stop on logpoints.
        messages = []
        while True:
            output_event = json_facade.wait_for_json_message(OutputEvent)
            msg = output_event.body.output
            ctx = output_event.body.category

            if ctx == 'stdout':
                msg = msg.strip()
                if msg == "var '_a' is 2":
                    messages.append(msg)

                if len(messages) == 2:
                    break

        # Just one hit at the end (break 3).
        hit = writer.wait_for_breakpoint_hit()
        writer.write_run_thread(hit.thread_id)

        writer.finished_ok = True


@pytest.mark.skipif(IS_JYTHON, reason='Must check why it is failing in Jython.')
def test_case_json_change_breaks(case_setup):
    with case_setup.test_file('_debugger_case_change_breaks.py') as writer:
        json_facade = JsonFacade(writer)

        writer.write_set_protocol('http_json')
        json_facade.write_launch()
        json_facade.write_set_breakpoints(writer.get_line_index_with_content('break 1'))
        json_facade.write_make_initial_run()
        hit = writer.wait_for_breakpoint_hit()
        writer.write_run_thread(hit.thread_id)

        hit = writer.wait_for_breakpoint_hit()
        writer.write_run_thread(hit.thread_id)

        json_facade.write_set_breakpoints([])
        writer.write_run_thread(hit.thread_id)

        writer.finished_ok = True


def test_case_handled_exception_breaks(case_setup):
    with case_setup.test_file('_debugger_case_exceptions.py') as writer:
        json_facade = JsonFacade(writer)

        writer.write_set_protocol('http_json')
        json_facade.write_launch()
        json_facade.write_set_exception_breakpoints(['raised'])
        json_facade.write_make_initial_run()

        hit = writer.wait_for_breakpoint_hit(
            reason=REASON_CAUGHT_EXCEPTION, line=writer.get_line_index_with_content('raise indexerror line'))
        writer.write_run_thread(hit.thread_id)

        hit = writer.wait_for_breakpoint_hit(
            reason=REASON_CAUGHT_EXCEPTION, line=writer.get_line_index_with_content('reraise on method2'))

        # Clear so that the last one is not hit.
        json_facade.write_set_exception_breakpoints([])
        writer.write_run_thread(hit.thread_id)

        writer.finished_ok = True


def test_case_handled_exception_breaks_by_type(case_setup):
    with case_setup.test_file('_debugger_case_exceptions.py') as writer:
        json_facade = JsonFacade(writer)

        writer.write_set_protocol('http_json')
        json_facade.write_launch()
        json_facade.write_set_exception_breakpoints(exception_options=[
            ExceptionOptions(breakMode='always', path=[
                {'names': ['Python Exceptions']},
                {'names': ['IndexError']},
            ])
        ])
        json_facade.write_make_initial_run()

        hit = writer.wait_for_breakpoint_hit(
            reason=REASON_CAUGHT_EXCEPTION, line=writer.get_line_index_with_content('raise indexerror line'))

        # Deal only with RuntimeErorr now.
        json_facade.write_set_exception_breakpoints(exception_options=[
            ExceptionOptions(breakMode='always', path=[
                {'names': ['Python Exceptions']},
                {'names': ['RuntimeError']},
            ])
        ])

        writer.write_run_thread(hit.thread_id)

        writer.finished_ok = True


@pytest.mark.skipif(IS_JYTHON, reason='Must check why it is failing in Jython.')
def test_case_json_protocol(case_setup):
    with case_setup.test_file('_debugger_case_print.py') as writer:
        json_facade = JsonFacade(writer)

        writer.write_set_protocol('http_json')
        json_facade.write_launch()
        json_facade.write_set_breakpoints(writer.get_line_index_with_content('Break here'))
        json_facade.write_make_initial_run()

        json_facade.wait_for_json_message(ThreadEvent, lambda event: event.body.reason == 'started')

        hit = writer.wait_for_breakpoint_hit()
        thread_id = hit.thread_id
        frame_id = hit.frame_id

        # : :type response: ThreadsResponse
        response = json_facade.write_list_threads()
        assert len(response.body.threads) == 1
        assert next(iter(response.body.threads))['name'] == 'MainThread'

        # Removes breakpoints and proceeds running.
        json_facade.write_disconnect()

        writer.finished_ok = True


@pytest.mark.parametrize("custom_setup", [
    'set_exclude_launch_module_full',
    'set_exclude_launch_module_prefix',
    'set_exclude_launch_path_match_filename',
    'set_exclude_launch_path_match_folder',
    'set_just_my_code',
    'set_just_my_code_and_include',
])
def test_case_skipping_filters(case_setup, custom_setup):
    with case_setup.test_file('my_code/my_code.py') as writer:
        json_facade = JsonFacade(writer)

        writer.write_set_protocol('http_json')
        if custom_setup == 'set_exclude_launch_path_match_filename':
            json_facade.write_launch(
                debugOptions=['DebugStdLib'],
                rules=[
                    {'path': '**/other.py', 'include':False},
                ]
            )

        elif custom_setup == 'set_exclude_launch_path_match_folder':
            json_facade.write_launch(
                debugOptions=['DebugStdLib'],
                rules=[
                    {'path': debugger_unittest._get_debugger_test_file('not_my_code'), 'include':False},
                ]
            )

        elif custom_setup == 'set_exclude_launch_module_full':
            json_facade.write_launch(
                debugOptions=['DebugStdLib'],
                rules=[
                    {'module': 'not_my_code.other', 'include':False},
                ]
            )

        elif custom_setup == 'set_exclude_launch_module_prefix':
            json_facade.write_launch(
                debugOptions=['DebugStdLib'],
                rules=[
                    {'module': 'not_my_code', 'include':False},
                ]
            )

        elif custom_setup == 'set_just_my_code':
            writer.write_set_project_roots([debugger_unittest._get_debugger_test_file('my_code')])
            json_facade.write_launch(debugOptions=[])

        elif custom_setup == 'set_just_my_code_and_include':
            # I.e.: nothing in my_code (add it with rule).
            writer.write_set_project_roots([debugger_unittest._get_debugger_test_file('launch')])
            json_facade.write_launch(
                debugOptions=[],
                rules=[
                    {'module': '__main__', 'include':True},
                ]
            )

        else:
            raise AssertionError('Unhandled: %s' % (custom_setup,))

        json_facade.write_set_breakpoints(writer.get_line_index_with_content('break here'))
        json_facade.write_make_initial_run()

        json_facade.wait_for_json_message(ThreadEvent, lambda event: event.body.reason == 'started')

        hit = writer.wait_for_breakpoint_hit()

        writer.write_step_in(hit.thread_id)
        hit = writer.wait_for_breakpoint_hit(reason=REASON_STEP_INTO)
        assert hit.name == 'callback1'

        writer.write_step_in(hit.thread_id)
        hit = writer.wait_for_breakpoint_hit(reason=REASON_STEP_INTO)
        assert hit.name == 'callback2'

        writer.write_step_over(hit.thread_id)
        hit = writer.wait_for_breakpoint_hit(reason=REASON_STEP_INTO)  # Note: goes from step over to step into
        assert hit.name == 'callback1'

        writer.write_step_over(hit.thread_id)
        hit = writer.wait_for_breakpoint_hit(reason=REASON_STEP_INTO)  # Note: goes from step over to step into
        assert hit.name == '<module>'

        writer.write_step_over(hit.thread_id)
        hit = writer.wait_for_breakpoint_hit(reason=REASON_STEP_OVER)
        assert hit.name == '<module>'

        writer.write_step_over(hit.thread_id)

        if IS_JYTHON:
            writer.write_run_thread(hit.thread_id)
        else:
            writer.write_step_over(hit.thread_id)

        writer.finished_ok = True


def test_case_completions_json(case_setup):
    with case_setup.test_file('_debugger_case_print.py') as writer:
        json_facade = JsonFacade(writer)

        writer.write_set_protocol('http_json')
        writer.write_add_breakpoint(writer.get_line_index_with_content('Break here'))

        json_facade.write_make_initial_run()

        hit = writer.wait_for_breakpoint_hit()

        json_hit = json_facade.get_stack_as_json_hit(hit.thread_id)

        completions_arguments = pydevd_schema.CompletionsArguments(
            'dict.', 6, frameId=json_hit.frameId, line=0)
        completions_request = json_facade.write_request(
            pydevd_schema.CompletionsRequest(completions_arguments))

        response = json_facade.wait_for_response(completions_request)
        labels = [x['label'] for x in response.body.targets]
        assert set(labels).issuperset(set(['__contains__', 'items', 'keys', 'values']))

        completions_arguments = pydevd_schema.CompletionsArguments(
            'dict.item', 10, frameId=json_hit.frameId)
        completions_request = json_facade.write_request(
            pydevd_schema.CompletionsRequest(completions_arguments))

        response = json_facade.wait_for_response(completions_request)
        if IS_JYTHON:
            assert response.body.targets == [
                {'start': 5, 'length': 4, 'type': 'keyword', 'label': 'items'}]
        else:
            assert response.body.targets == [
                {'start': 5, 'length': 4, 'type': 'function', 'label': 'items'}]

        writer.write_run_thread(hit.thread_id)

        writer.finished_ok = True


def test_modules(case_setup):
    with case_setup.test_file('_debugger_case_local_variables.py') as writer:
        json_facade = JsonFacade(writer)

        writer.write_set_protocol('http_json')

        writer.write_add_breakpoint(writer.get_line_index_with_content('Break 2 here'))
        json_facade.write_make_initial_run()

        hit = writer.wait_for_breakpoint_hit()

        json_facade.write_request(
            pydevd_schema.StackTraceRequest(pydevd_schema.StackTraceArguments(threadId=hit.thread_id)))

        json_facade.wait_for_json_message(ModuleEvent)

        # : :type response: ModulesResponse
        # : :type modules_response_body: ModulesResponseBody
        response = json_facade.wait_for_response(json_facade.write_request(
            pydevd_schema.ModulesRequest(pydevd_schema.ModulesArguments())))
        modules_response_body = response.body
        assert len(modules_response_body.modules) == 1
        module = next(iter(modules_response_body.modules))
        assert module['name'] == '__main__'
        assert module['path'].endswith('_debugger_case_local_variables.py')

        writer.write_run_thread(hit.thread_id)
        writer.finished_ok = True


@pytest.mark.skipif(IS_JYTHON, reason='Putting unicode on frame vars does not work on Jython.')
def test_stack_and_variables_dict(case_setup):
    with case_setup.test_file('_debugger_case_local_variables.py') as writer:
        json_facade = JsonFacade(writer)

        writer.write_set_protocol('http_json')

        writer.write_add_breakpoint(writer.get_line_index_with_content('Break 2 here'))
        json_facade.write_make_initial_run()

        hit = writer.wait_for_breakpoint_hit()
        json_hit = json_facade.get_stack_as_json_hit(hit.thread_id)
        variables_response = json_facade.get_variables_response(json_hit.frameId)

        variables_references = json_facade.pop_variables_reference(variables_response.body.variables)
        dict_variable_reference = variables_references[2]
        assert isinstance(dict_variable_reference, int_types)
        # : :type variables_response: VariablesResponse

        if IS_PY2:
            print(repr(variables_response.body.variables[-1]))
            expected_unicode = {
                u'name': u'\u16a0',
                u'value': u"u'\\u16a1'",
                u'type': u'unicode',
                u'presentationHint': {u'attributes': [u'rawString']},
                u'evaluateName': u'\u16a0',
            }
        else:
            expected_unicode = {
                'name': u'\u16A0',
                'value': "'\u16a1'",
                'type': 'str',
                'presentationHint': {'attributes': ['rawString']},
                'evaluateName': u'\u16A0',
            }
        assert variables_response.body.variables == [
            {'name': 'variable_for_test_1', 'value': '10', 'type': 'int', 'evaluateName': 'variable_for_test_1'},
            {'name': 'variable_for_test_2', 'value': '20', 'type': 'int', 'evaluateName': 'variable_for_test_2'},
            {'name': 'variable_for_test_3', 'value': "{'a': 30, 'b': 20}", 'type': 'dict', 'evaluateName': 'variable_for_test_3'},
            expected_unicode
        ]

        variables_response = json_facade.get_variables_response(dict_variable_reference)
        assert variables_response.body.variables == [
            {'name': "'a'", 'value': '30', 'type': 'int', 'evaluateName': "variable_for_test_3['a']" },
            {'name': "'b'", 'value': '20', 'type': 'int', 'evaluateName': "variable_for_test_3['b']"},
            {'name': '__len__', 'value': '2', 'type': 'int', 'evaluateName': 'len(variable_for_test_3)'}
        ]

        writer.write_run_thread(hit.thread_id)
        writer.finished_ok = True


def test_return_value(case_setup):
    with case_setup.test_file('_debugger_case_return_value.py') as writer:
        json_facade = JsonFacade(writer)
        writer.write_set_protocol('http_json')

        break_line = writer.get_line_index_with_content('break here')
        writer.write_add_breakpoint(break_line)
        writer.write_show_return_vars()
        json_facade.write_make_initial_run()

        hit = writer.wait_for_breakpoint_hit()
        writer.write_step_over(hit.thread_id)
        hit = writer.wait_for_breakpoint_hit(REASON_STEP_OVER, name='<module>', line=break_line + 1)

        json_hit = json_facade.get_stack_as_json_hit(hit.thread_id)
        variables_response = json_facade.get_variables_response(json_hit.frameId)
        return_variables = json_facade.filter_return_variables(variables_response.body.variables)
        assert return_variables == [{
            'name': '(return) method1',
            'value': '1',
            'type': 'int',
            'evaluateName': "__pydevd_ret_val_dict['method1']",
            'presentationHint': {'attributes': ['readOnly']}
        }]

        writer.write_run_thread(hit.thread_id)
        writer.finished_ok = True


def test_stack_and_variables_set_and_list(case_setup):
    with case_setup.test_file('_debugger_case_local_variables2.py') as writer:
        json_facade = JsonFacade(writer)

        writer.write_set_protocol('http_json')

        writer.write_add_breakpoint(writer.get_line_index_with_content('Break here'))
        json_facade.write_make_initial_run()

        hit = writer.wait_for_breakpoint_hit()
        json_hit = json_facade.get_stack_as_json_hit(hit.thread_id)
        variables_response = json_facade.get_variables_response(json_hit.frameId)

        variables_references = json_facade.pop_variables_reference(variables_response.body.variables)
        if IS_PY2:
            expected_set = "set(['a'])"
        else:
            expected_set = "{'a'}"
        assert variables_response.body.variables == [
            {'type': 'list', 'evaluateName': 'variable_for_test_1', 'name': 'variable_for_test_1', 'value': "['a', 'b']"},
            {'type': 'set', 'evaluateName': 'variable_for_test_2', 'name': 'variable_for_test_2', 'value': expected_set}
        ]

        variables_response = json_facade.get_variables_response(variables_references[0])
        assert variables_response.body.variables == [{
            u'name': u'0',
            u'type': u'str',
            u'value': u"'a'",
            u'presentationHint': {u'attributes': [u'rawString']},
            u'evaluateName': u'variable_for_test_1[0]',
        },
        {
            u'name': u'1',
            u'type': u'str',
            u'value': u"'b'",
            u'presentationHint': {u'attributes': [u'rawString']},
            u'evaluateName': u'variable_for_test_1[1]',
        },
        {
            u'name': u'__len__',
            u'type': u'int',
            u'value': u'2',
            u'evaluateName': u'len(variable_for_test_1)',
        }]

        writer.write_run_thread(hit.thread_id)
        writer.finished_ok = True


@pytest.mark.skipif(IS_JYTHON, reason='Putting unicode on frame vars does not work on Jython.')
def test_evaluate_unicode(case_setup):
    from _pydevd_bundle._debug_adapter.pydevd_schema import EvaluateRequest
    from _pydevd_bundle._debug_adapter.pydevd_schema import EvaluateArguments
    with case_setup.test_file('_debugger_case_local_variables.py') as writer:
        json_facade = JsonFacade(writer)

        writer.write_set_protocol('http_json')

        writer.write_add_breakpoint(writer.get_line_index_with_content('Break 2 here'))
        json_facade.write_make_initial_run()

        hit = writer.wait_for_breakpoint_hit()
        json_hit = json_facade.get_stack_as_json_hit(hit.thread_id)

        evaluate_response = json_facade.wait_for_response(
            json_facade.write_request(EvaluateRequest(EvaluateArguments(u'\u16A0', json_hit.frameId))))

        evaluate_response_body = evaluate_response.body.to_dict()

        if IS_PY2:
            # The error can be referenced.
            variables_reference = json_facade.pop_variables_reference([evaluate_response_body])

            assert evaluate_response_body == {
                'result': u"SyntaxError('invalid syntax', ('<string>', 1, 1, '\\xe1\\x9a\\xa0'))",
                'type': u'SyntaxError',
                'presentationHint': {},
            }

            assert len(variables_reference) == 1
            reference = variables_reference[0]
            assert reference > 0
            variables_response = json_facade.get_variables_response(reference)
            child_variables = variables_response.to_dict()['body']['variables']
            assert len(child_variables) == 1
            assert json_facade.pop_variables_reference(child_variables)[0] > 0
            assert child_variables == [{
                u'type': u'SyntaxError',
                u'evaluateName': u'\u16a0.result',
                u'name': u'result',
                u'value': u"SyntaxError('invalid syntax', ('<string>', 1, 1, '\\xe1\\x9a\\xa0'))"
            }]

        else:
            assert evaluate_response_body == {
                'result': "'\u16a1'",
                'type': 'str',
                'variablesReference': 0,
                'presentationHint': {'attributes': ['rawString']},
            }

        writer.write_run_thread(hit.thread_id)
        writer.finished_ok = True


def test_evaluate_variable_references(case_setup):
    from _pydevd_bundle._debug_adapter.pydevd_schema import EvaluateRequest
    from _pydevd_bundle._debug_adapter.pydevd_schema import EvaluateArguments
    with case_setup.test_file('_debugger_case_local_variables2.py') as writer:
        json_facade = JsonFacade(writer)

        writer.write_set_protocol('http_json')

        writer.write_add_breakpoint(writer.get_line_index_with_content('Break here'))
        json_facade.write_make_initial_run()

        hit = writer.wait_for_breakpoint_hit()
        json_hit = json_facade.get_stack_as_json_hit(hit.thread_id)

        evaluate_response = json_facade.wait_for_response(
            json_facade.write_request(EvaluateRequest(EvaluateArguments('variable_for_test_2', json_hit.frameId))))

        evaluate_response_body = evaluate_response.body.to_dict()

        variables_reference = json_facade.pop_variables_reference([evaluate_response_body])

        assert evaluate_response_body == {
            'type': 'set',
            'result': "set(['a'])" if IS_PY2 else "{'a'}",
            'presentationHint': {},
        }
        assert len(variables_reference) == 1
        reference = variables_reference[0]
        assert reference > 0
        variables_response = json_facade.get_variables_response(reference)
        child_variables = variables_response.to_dict()['body']['variables']

        # The name for a reference in a set is the id() of the variable and can change at each run.
        del child_variables[0]['name']

        assert child_variables == [
            {
                'type': 'str',
                'value': "'a'",
                'presentationHint': {'attributes': ['rawString']},
            },
            {
                'name': '__len__',
                'type': 'int',
                'value': '1'
            }
        ]

        writer.write_run_thread(hit.thread_id)
        writer.finished_ok = True


def test_set_expression(case_setup):
    from _pydevd_bundle._debug_adapter.pydevd_schema import SetExpressionRequest
    from _pydevd_bundle._debug_adapter.pydevd_schema import SetExpressionArguments
    with case_setup.test_file('_debugger_case_local_variables2.py') as writer:
        json_facade = JsonFacade(writer)

        writer.write_set_protocol('http_json')

        writer.write_add_breakpoint(writer.get_line_index_with_content('Break here'))
        json_facade.write_make_initial_run()

        hit = writer.wait_for_breakpoint_hit()
        json_hit = json_facade.get_stack_as_json_hit(hit.thread_id)

        set_expression_response = json_facade.wait_for_response(
            json_facade.write_request(SetExpressionRequest(
                SetExpressionArguments('bb', '20', frameId=json_hit.frameId))))
        assert set_expression_response.to_dict()['body'] == {
            'value': '20', 'type': 'int', 'presentationHint': {}, 'variablesReference': 0}

        variables_response = json_facade.get_variables_response(json_hit.frameId)
        assert {'name': 'bb', 'value': '20', 'type': 'int', 'evaluateName': 'bb'} in \
            variables_response.to_dict()['body']['variables']

        writer.write_run_thread(hit.thread_id)
        writer.finished_ok = True


@pytest.mark.skipif(IS_JYTHON, reason='Putting unicode on frame vars does not work on Jython.')
def test_stack_and_variables(case_setup):

    with case_setup.test_file('_debugger_case_local_variables.py') as writer:
        json_facade = JsonFacade(writer)

        writer.write_set_protocol('http_json')
        writer.write_add_breakpoint(writer.get_line_index_with_content('Break here'))

        json_facade.write_make_initial_run()

        hit = writer.wait_for_breakpoint_hit()

        # : :type stack_trace_response: StackTraceResponse
        # : :type stack_trace_response_body: StackTraceResponseBody
        # : :type stack_frame: StackFrame

        # Check stack trace format.
        stack_trace_request = json_facade.write_request(
            pydevd_schema.StackTraceRequest(pydevd_schema.StackTraceArguments(
                threadId=hit.thread_id,
                format={'module': True, 'line': True}
        )))
        stack_trace_response = json_facade.wait_for_response(stack_trace_request)
        stack_trace_response_body = stack_trace_response.body
        stack_frame = next(iter(stack_trace_response_body.stackFrames))
        assert stack_frame['name'] == '__main__.Call : 4'

        # Regular stack trace request (no format).
        stack_trace_request = json_facade.write_request(
            pydevd_schema.StackTraceRequest(pydevd_schema.StackTraceArguments(threadId=hit.thread_id)))
        stack_trace_response = json_facade.wait_for_response(stack_trace_request)
        stack_trace_response_body = stack_trace_response.body
        assert len(stack_trace_response_body.stackFrames) == 2
        stack_frame = next(iter(stack_trace_response_body.stackFrames))
        assert stack_frame['name'] == 'Call'
        assert stack_frame['source']['path'].endswith('_debugger_case_local_variables.py')

        scopes_request = json_facade.write_request(pydevd_schema.ScopesRequest(
            pydevd_schema.ScopesArguments(stack_frame['id'])))

        scopes_response = json_facade.wait_for_response(scopes_request)
        scopes = scopes_response.body.scopes
        assert len(scopes) == 1
        scope = pydevd_schema.Scope(**next(iter(scopes)))
        assert scope.name == 'Locals'
        assert not scope.expensive
        frame_variables_reference = scope.variablesReference
        assert isinstance(frame_variables_reference, int)

        variables_request = json_facade.write_request(
            pydevd_schema.VariablesRequest(pydevd_schema.VariablesArguments(frame_variables_reference)))
        variables_response = json_facade.wait_for_response(variables_request)
        # : :type variables_response: VariablesResponse
        assert len(variables_response.body.variables) == 0  # No variables expected here

        writer.write_step_over(hit.thread_id)
        hit = writer.wait_for_breakpoint_hit(REASON_STEP_OVER)

        variables_request = json_facade.write_request(
            pydevd_schema.VariablesRequest(pydevd_schema.VariablesArguments(frame_variables_reference)))
        variables_response = json_facade.wait_for_response(variables_request)
        # : :type variables_response: VariablesResponse
        assert variables_response.body.variables == [{
            'name': 'variable_for_test_1',
            'value': '10',
            'type': 'int',
            'evaluateName': 'variable_for_test_1'
        }]

        # Same thing with hex format
        variables_request = json_facade.write_request(
            pydevd_schema.VariablesRequest(pydevd_schema.VariablesArguments(
                frame_variables_reference,
                format={'hex': True}
            )))
        variables_response = json_facade.wait_for_response(variables_request)
        # : :type variables_response: VariablesResponse
        assert variables_response.body.variables == [{
            'name': 'variable_for_test_1',
            'value': '0xa',
            'type': 'int',
            'evaluateName': 'variable_for_test_1'
        }]

        # Note: besides the scope/stack/variables we can also have references when:
        # - setting variable
        #    * If the variable was changed to a container, the new reference should be returned.
        # - evaluate expression
        #    * Currently ptvsd returns a None value in on_setExpression, so, skip this for now.
        # - output
        #    * Currently not handled by ptvsd, so, skip for now.

        # Reference is for parent (in this case the frame).
        # We'll change `variable_for_test_1` from 10 to [1].
        set_variable_request = json_facade.write_request(
            pydevd_schema.SetVariableRequest(pydevd_schema.SetVariableArguments(
                frame_variables_reference, 'variable_for_test_1', '[1]'
        )))
        set_variable_response = json_facade.wait_for_response(set_variable_request)
        set_variable_response_as_dict = set_variable_response.to_dict()['body']
        if not IS_JYTHON:
            # Not properly changing var on Jython.
            assert isinstance(set_variable_response_as_dict.pop('variablesReference'), int)
            assert set_variable_response_as_dict == {'value': "[1]", 'type': 'list'}

        variables_request = json_facade.write_request(
            pydevd_schema.VariablesRequest(pydevd_schema.VariablesArguments(frame_variables_reference)))
        variables_response = json_facade.wait_for_response(variables_request)
        # : :type variables_response: VariablesResponse
        variables = variables_response.body.variables
        assert len(variables) == 1
        var_as_dict = next(iter(variables))
        if not IS_JYTHON:
            # Not properly changing var on Jython.
            assert isinstance(var_as_dict.pop('variablesReference'), int)
            assert var_as_dict == {
                'name': 'variable_for_test_1',
                'value': "[1]",
                'type': 'list',
                'evaluateName': 'variable_for_test_1',
            }

        writer.write_run_thread(hit.thread_id)

        writer.finished_ok = True


def test_hex_variables(case_setup):
    with case_setup.test_file('_debugger_case_local_variables_hex.py') as writer:
        json_facade = JsonFacade(writer)

        writer.write_set_protocol('http_json')
        writer.write_add_breakpoint(writer.get_line_index_with_content('Break here'))

        json_facade.write_make_initial_run()

        hit = writer.wait_for_breakpoint_hit()

        # : :type stack_trace_response: StackTraceResponse
        # : :type stack_trace_response_body: StackTraceResponseBody
        # : :type stack_frame: StackFrame
        stack_trace_request = json_facade.write_request(
            pydevd_schema.StackTraceRequest(pydevd_schema.StackTraceArguments(threadId=hit.thread_id)))
        stack_trace_response = json_facade.wait_for_response(stack_trace_request)
        stack_trace_response_body = stack_trace_response.body
        assert len(stack_trace_response_body.stackFrames) == 2
        stack_frame = next(iter(stack_trace_response_body.stackFrames))
        assert stack_frame['name'] == 'Call'
        assert stack_frame['source']['path'].endswith('_debugger_case_local_variables_hex.py')

        scopes_request = json_facade.write_request(pydevd_schema.ScopesRequest(
            pydevd_schema.ScopesArguments(stack_frame['id'])))

        scopes_response = json_facade.wait_for_response(scopes_request)
        scopes = scopes_response.body.scopes
        assert len(scopes) == 1
        scope = pydevd_schema.Scope(**next(iter(scopes)))
        assert scope.name == 'Locals'
        assert not scope.expensive
        frame_variables_reference = scope.variablesReference
        assert isinstance(frame_variables_reference, int)

        fmt = {'hex': True}
        variables_request = json_facade.write_request(
            pydevd_schema.VariablesRequest(pydevd_schema.VariablesArguments(frame_variables_reference, format=fmt)))
        variables_response = json_facade.wait_for_response(variables_request)

        # : :type variables_response: VariablesResponse
        variable_for_test_1, variable_for_test_2, variable_for_test_3, variable_for_test_4 = sorted(list(
            v for v in variables_response.body.variables if v['name'].startswith('variables_for_test')
        ), key=lambda v: v['name'])
        assert variable_for_test_1 == {
            'name': 'variables_for_test_1',
            'value': "0x64",
            'type': 'int',
            'evaluateName': 'variables_for_test_1'
        }

        assert isinstance(variable_for_test_2.pop('variablesReference'), int)
        assert variable_for_test_2 == {
            'name': 'variables_for_test_2',
            'value': "[0x1, 0xa, 0x64]",
            'type': 'list',
            'evaluateName': 'variables_for_test_2'
        }

        assert isinstance(variable_for_test_3.pop('variablesReference'), int)
        assert variable_for_test_3 == {
            'name': 'variables_for_test_3',
            'value': '{0xa: 0xa, 0x64: 0x64, 0x3e8: 0x3e8}',
            'type': 'dict',
            'evaluateName': 'variables_for_test_3'
        }

        assert isinstance(variable_for_test_4.pop('variablesReference'), int)
        assert variable_for_test_4 == {
            'name': 'variables_for_test_4',
            'value': '{(0x1, 0xa, 0x64): (0x2710, 0x186a0, 0x186a0)}',
            'type': 'dict',
            'evaluateName': 'variables_for_test_4'
        }

        writer.write_run_thread(hit.thread_id)

        writer.finished_ok = True


@pytest.mark.skipif(IS_JYTHON, reason='Flaky on Jython.')
def test_pause_and_continue(case_setup):
    with case_setup.test_file('_debugger_case_pause_continue.py') as writer:
        json_facade = JsonFacade(writer)

        writer.write_multi_threads_single_notification(True)
        writer.write_set_protocol('http_json')
        writer.write_add_breakpoint(writer.get_line_index_with_content('Break here'))

        json_facade.write_make_initial_run()

        hit = writer.wait_for_breakpoint_hit()

        continue_request = json_facade.write_request(
            pydevd_schema.ContinueRequest(pydevd_schema.ContinueArguments('*')))
        continue_response = json_facade.wait_for_response(continue_request)
        assert continue_response.body.allThreadsContinued

        pause_request = json_facade.write_request(
            pydevd_schema.PauseRequest(pydevd_schema.PauseArguments('*')))
        pause_response = json_facade.wait_for_response(pause_request)
        hit = writer.wait_for_breakpoint_hit(reason=REASON_THREAD_SUSPEND)

        stack_trace_request = json_facade.write_request(
            pydevd_schema.StackTraceRequest(pydevd_schema.StackTraceArguments(threadId=hit.thread_id)))
        stack_trace_response = json_facade.wait_for_response(stack_trace_request)
        stack_frame = next(iter(stack_trace_response.body.stackFrames))

        scopes_request = json_facade.write_request(pydevd_schema.ScopesRequest(
            pydevd_schema.ScopesArguments(stack_frame['id'])))
        scopes_response = json_facade.wait_for_response(scopes_request)
        scope = pydevd_schema.Scope(**next(iter(scopes_response.body.scopes)))
        frame_variables_reference = scope.variablesReference

        set_variable_request = json_facade.write_request(
            pydevd_schema.SetVariableRequest(pydevd_schema.SetVariableArguments(
                frame_variables_reference, 'loop', 'False'
        )))
        set_variable_response = json_facade.wait_for_response(set_variable_request)
        set_variable_response_as_dict = set_variable_response.to_dict()['body']
        assert set_variable_response_as_dict == {'value': "False", 'type': 'bool'}

        continue_request = json_facade.write_request(
        pydevd_schema.ContinueRequest(pydevd_schema.ContinueArguments('*')))
        continue_response = json_facade.wait_for_response(continue_request)
        assert continue_response.body.allThreadsContinued

        writer.finished_ok = True


def test_stepping(case_setup):
    with case_setup.test_file('_debugger_case_stepping.py') as writer:
        json_facade = JsonFacade(writer)

        writer.write_set_protocol('http_json')
        writer.write_add_breakpoint(writer.get_line_index_with_content('Break here 1'))
        writer.write_add_breakpoint(writer.get_line_index_with_content('Break here 2'))

        json_facade.write_make_initial_run()

        hit = writer.wait_for_breakpoint_hit()

        # Test Step-Over or 'next'
        stack_trace_request = json_facade.write_request(
            pydevd_schema.StackTraceRequest(pydevd_schema.StackTraceArguments(threadId=hit.thread_id)))
        stack_trace_response = json_facade.wait_for_response(stack_trace_request)
        stack_frame = next(iter(stack_trace_response.body.stackFrames))
        before_step_over_line = stack_frame['line']

        next_request = json_facade.write_request(
            pydevd_schema.NextRequest(pydevd_schema.NextArguments(hit.thread_id)))
        next_response = json_facade.wait_for_response(next_request)
        hit = writer.wait_for_breakpoint_hit(REASON_STEP_OVER)

        stack_trace_request = json_facade.write_request(
            pydevd_schema.StackTraceRequest(pydevd_schema.StackTraceArguments(threadId=hit.thread_id)))
        stack_trace_response = json_facade.wait_for_response(stack_trace_request)
        stack_frame = next(iter(stack_trace_response.body.stackFrames))
        after_step_over_line = stack_frame['line']

        assert int(before_step_over_line) + 1 == int(after_step_over_line)

        # Test step into or 'stepIn'
        stepin_request = json_facade.write_request(
            pydevd_schema.StepInRequest(pydevd_schema.StepInArguments(hit.thread_id)))
        stepin_response = json_facade.wait_for_response(stepin_request)
        hit = writer.wait_for_breakpoint_hit(REASON_STEP_INTO)

        stack_trace_request = json_facade.write_request(
            pydevd_schema.StackTraceRequest(pydevd_schema.StackTraceArguments(threadId=hit.thread_id)))
        stack_trace_response = json_facade.wait_for_response(stack_trace_request)
        stack_frame = next(iter(stack_trace_response.body.stackFrames))

        assert stack_frame['name'] == 'step_into'

        # Test step return or 'stepOut'
        writer.write_run_thread(hit.thread_id)
        hit = writer.wait_for_breakpoint_hit()

        stack_trace_request = json_facade.write_request(
            pydevd_schema.StackTraceRequest(pydevd_schema.StackTraceArguments(threadId=hit.thread_id)))
        stack_trace_response = json_facade.wait_for_response(stack_trace_request)
        stack_frame = next(iter(stack_trace_response.body.stackFrames))
        assert stack_frame['name'] == 'step_out'

        stepout_request = json_facade.write_request(
            pydevd_schema.StepOutRequest(pydevd_schema.StepOutArguments(hit.thread_id)))
        stepout_response = json_facade.wait_for_response(stepout_request)
        hit = writer.wait_for_breakpoint_hit(REASON_STEP_RETURN)

        stack_trace_request = json_facade.write_request(
            pydevd_schema.StackTraceRequest(pydevd_schema.StackTraceArguments(threadId=hit.thread_id)))
        stack_trace_response = json_facade.wait_for_response(stack_trace_request)
        stack_frame = next(iter(stack_trace_response.body.stackFrames))
        assert stack_frame['name'] == 'Call'

        writer.write_run_thread(hit.thread_id)

        writer.finished_ok = True


def test_evaluate(case_setup):
    with case_setup.test_file('_debugger_case_evaluate.py') as writer:
        json_facade = JsonFacade(writer)

        writer.write_set_protocol('http_json')
        writer.write_add_breakpoint(writer.get_line_index_with_content('Break here'))

        json_facade.write_make_initial_run()

        hit = writer.wait_for_breakpoint_hit()

        stack_trace_request = json_facade.write_request(
            pydevd_schema.StackTraceRequest(pydevd_schema.StackTraceArguments(threadId=hit.thread_id)))
        stack_trace_response = json_facade.wait_for_response(stack_trace_request)
        stack_frame = next(iter(stack_trace_response.body.stackFrames))
        stack_frame_id = stack_frame['id']

        # Test evaluate request that results in 'eval'
        eval_request = json_facade.write_request(
            pydevd_schema.EvaluateRequest(pydevd_schema.EvaluateArguments('var_1', frameId=stack_frame_id, context='repl')))
        eval_response = json_facade.wait_for_response(eval_request)
        assert eval_response.body.result == '5'
        assert eval_response.body.type == 'int'

        # Test evaluate request that results in 'exec'
        exec_request = json_facade.write_request(
            pydevd_schema.EvaluateRequest(pydevd_schema.EvaluateArguments('var_1 = 6', frameId=stack_frame_id, context='repl')))
        exec_response = json_facade.wait_for_response(exec_request)
        assert exec_response.body.result == ''

        # Test evaluate request that results in 'exec' but fails
        exec_request = json_facade.write_request(
            pydevd_schema.EvaluateRequest(pydevd_schema.EvaluateArguments('var_1 = "abc"/6', frameId=stack_frame_id, context='repl')))
        exec_response = json_facade.wait_for_response(exec_request)
        assert exec_response.success == False
        assert exec_response.body.result == ''
        assert exec_response.message.find('TypeError') > -1

        writer.write_run_thread(hit.thread_id)

        writer.finished_ok = True


def test_exception_details(case_setup):
    with case_setup.test_file('_debugger_case_exceptions.py') as writer:
        json_facade = JsonFacade(writer)

        writer.write_set_protocol('http_json')
        json_facade.write_set_exception_breakpoints(['raised'])

        json_facade.write_make_initial_run()
        hit = writer.wait_for_breakpoint_hit(REASON_CAUGHT_EXCEPTION)

        exc_info_request = json_facade.write_request(
            pydevd_schema.ExceptionInfoRequest(pydevd_schema.ExceptionInfoArguments(hit.thread_id)))
        exc_info_response = json_facade.wait_for_response(exc_info_request)
        body = exc_info_response.body
        assert body.exceptionId.endswith('IndexError')
        assert body.description == 'foo'
        assert body.details.kwargs['source'] == writer.TEST_FILE

        json_facade.write_set_exception_breakpoints([])  # Don't stop on reraises.
        writer.write_run_thread(hit.thread_id)

        writer.finished_ok = True


@pytest.mark.skipif(IS_JYTHON, reason='No goto on Jython.')
def test_goto(case_setup):
    with case_setup.test_file('_debugger_case_set_next_statement.py') as writer:
        json_facade = JsonFacade(writer)

        writer.write_set_protocol('http_json')
        break_line = writer.get_line_index_with_content('Break here')
        step_line = writer.get_line_index_with_content('Step here')
        writer.write_add_breakpoint(break_line)

        json_facade.write_make_initial_run()

        hit = writer.wait_for_breakpoint_hit()

        stack_trace_request = json_facade.write_request(
            pydevd_schema.StackTraceRequest(pydevd_schema.StackTraceArguments(threadId=hit.thread_id)))
        stack_trace_response = json_facade.wait_for_response(stack_trace_request)
        stack_frame = next(iter(stack_trace_response.body.stackFrames))
        assert stack_frame['line'] == break_line

        goto_targets_request = json_facade.write_request(
            pydevd_schema.GotoTargetsRequest(pydevd_schema.GotoTargetsArguments(
                source=pydevd_schema.Source(path=writer.TEST_FILE, sourceReference=0),
                line=step_line)))
        goto_targets_response = json_facade.wait_for_response(goto_targets_request)
        target_id = goto_targets_response.body.targets[0]['id']

        goto_request = json_facade.write_request(
            pydevd_schema.GotoRequest(pydevd_schema.GotoArguments(
                threadId=hit.thread_id,
                targetId=12345)))
        goto_response = json_facade.wait_for_response(goto_request)
        assert not goto_response.success

        goto_request = json_facade.write_request(
            pydevd_schema.GotoRequest(pydevd_schema.GotoArguments(
                threadId=hit.thread_id,
                targetId=target_id)))
        goto_response = json_facade.wait_for_response(goto_request)

        hit = writer.wait_for_breakpoint_hit(reason='127')

        stack_trace_request = json_facade.write_request(
            pydevd_schema.StackTraceRequest(pydevd_schema.StackTraceArguments(threadId=hit.thread_id)))
        stack_trace_response = json_facade.wait_for_response(stack_trace_request)
        stack_frame = next(iter(stack_trace_response.body.stackFrames))
        assert stack_frame['line'] == step_line

        writer.write_run_thread(hit.thread_id)

        # we hit the breakpoint again. Since we moved back
        hit = writer.wait_for_breakpoint_hit()
        writer.write_run_thread(hit.thread_id)

        writer.finished_ok = True


@pytest.mark.skipif(IS_JYTHON, reason='Flaky on Jython.')
def test_path_translation_and_source_reference(case_setup):

    def get_file_in_client(writer):
        # Instead of using: test_python/_debugger_case_path_translation.py
        # we'll set the breakpoints at foo/_debugger_case_path_translation.py
        file_in_client = os.path.dirname(os.path.dirname(writer.TEST_FILE))
        return os.path.join(os.path.dirname(file_in_client), 'foo', '_debugger_case_path_translation.py')

    def get_environ(writer):
        env = os.environ.copy()

        env["PYTHONIOENCODING"] = 'utf-8'

        assert writer.TEST_FILE.endswith('_debugger_case_path_translation.py')
        env["PATHS_FROM_ECLIPSE_TO_PYTHON"] = json.dumps([
            (
                os.path.dirname(get_file_in_client(writer)),
                os.path.dirname(writer.TEST_FILE)
            )
        ])
        return env

    with case_setup.test_file('_debugger_case_path_translation.py', get_environ=get_environ) as writer:
        file_in_client = get_file_in_client(writer)
        assert 'tests_python' not in file_in_client
        assert 'foo' in file_in_client

        json_facade = JsonFacade(writer)

        writer.write_set_protocol('http_json')
        bp_line = writer.get_line_index_with_content('break here')
        writer.write_add_breakpoint(
            bp_line, 'call_this', filename=file_in_client)

        json_facade.write_make_initial_run()

        hit = writer.wait_for_breakpoint_hit()

        # : :type stack_trace_response: StackTraceResponse
        # : :type stack_trace_response_body: StackTraceResponseBody
        # : :type stack_frame: StackFrame

        # Check stack trace format.
        stack_trace_request = json_facade.write_request(
            pydevd_schema.StackTraceRequest(pydevd_schema.StackTraceArguments(
                threadId=hit.thread_id,
                format={'module': True, 'line': True}
        )))
        stack_trace_response = json_facade.wait_for_response(stack_trace_request)
        stack_trace_response_body = stack_trace_response.body
        stack_frame = stack_trace_response_body.stackFrames[0]
        assert stack_frame['name'] == '__main__.call_this : %s' % (bp_line,)
        assert stack_frame['source']['path'] == file_in_client
        source_reference = stack_frame['source']['sourceReference']
        assert source_reference == 0  # When it's translated the source reference must be == 0

        stack_frame_not_path_translated = stack_trace_response_body.stackFrames[1]
        assert stack_frame_not_path_translated['name'].startswith(
            'tests_python.resource_path_translation.other.call_me_back1 :')

        assert stack_frame_not_path_translated['source']['path'].endswith('other.py')
        source_reference = stack_frame_not_path_translated['source']['sourceReference']
        assert source_reference != 0  # Not translated

        response = json_facade.wait_for_response(json_facade.write_request(
            pydevd_schema.SourceRequest(pydevd_schema.SourceArguments(source_reference))))
        assert "def call_me_back1(callback):" in response.body.content

        writer.write_run_thread(hit.thread_id)

        writer.finished_ok = True


@pytest.mark.skipif(IS_JYTHON, reason='Flaky on Jython.')
def test_source_reference_no_file(case_setup, tmpdir):

    def get_environ(writer):
        env = os.environ.copy()
        # We need to set up path mapping to enable source references.
        env["PATHS_FROM_ECLIPSE_TO_PYTHON"] = json.dumps([
            (os.path.dirname(writer.TEST_FILE), os.path.dirname(writer.TEST_FILE))
        ])
        return env

    with case_setup.test_file('_debugger_case_source_reference.py', get_environ=get_environ) as writer:
        json_facade = JsonFacade(writer)
        writer.write_set_protocol('http_json')
        writer.write_add_breakpoint(writer.get_line_index_with_content('breakpoint'))
        json_facade.write_make_initial_run()

        # First hit is for breakpoint reached via a stack frame that doesn't have source.

        hit = writer.wait_for_breakpoint_hit()
        stack_trace_request = json_facade.write_request(
            pydevd_schema.StackTraceRequest(pydevd_schema.StackTraceArguments(
                threadId=hit.thread_id,
                format={'module': True, 'line': True}
        )))
        stack_trace_response = json_facade.wait_for_response(stack_trace_request)
        stack_trace_response_body = stack_trace_response.body
        stack_frame = stack_trace_response_body.stackFrames[1]
        assert stack_frame['source']['path'] == '<string>'
        source_reference = stack_frame['source']['sourceReference']
        assert source_reference != 0

        response = json_facade.wait_for_response(json_facade.write_request(
            pydevd_schema.SourceRequest(pydevd_schema.SourceArguments(source_reference))))
        assert not response.success

        writer.write_run_thread(hit.thread_id)

        # First hit is for breakpoint reached via a stack frame that doesn't have source
        # on disk, but which can be retrieved via linecache.

        hit = writer.wait_for_breakpoint_hit()
        stack_trace_request = json_facade.write_request(
            pydevd_schema.StackTraceRequest(pydevd_schema.StackTraceArguments(
                threadId=hit.thread_id,
                format={'module': True, 'line': True}
        )))
        stack_trace_response = json_facade.wait_for_response(stack_trace_request)
        stack_trace_response_body = stack_trace_response.body
        stack_frame = stack_trace_response_body.stackFrames[1]
        print(stack_frame['source']['path'])
        assert stack_frame['source']['path'] == '<something>'
        source_reference = stack_frame['source']['sourceReference']
        assert source_reference != 0

        response = json_facade.wait_for_response(json_facade.write_request(
            pydevd_schema.SourceRequest(pydevd_schema.SourceArguments(source_reference))))
        assert response.success
        assert response.body.content == 'foo()\n'

        writer.write_run_thread(hit.thread_id)
        writer.finished_ok = True


@pytest.mark.skipif(not TEST_DJANGO, reason='No django available')
@pytest.mark.parametrize("jmc", [False, True])
def test_case_django_no_attribute_exception_breakpoint(case_setup_django, jmc):
    django_version = [int(x) for x in django.get_version().split('.')][:2]

    if django_version < [2, 1]:
        pytest.skip('Template exceptions only supporting Django 2.1 onwards.')

    with case_setup_django.test_file(EXPECTED_RETURNCODE='any') as writer:
        json_facade = JsonFacade(writer)
        writer.write_set_protocol('http_json')

        if jmc:
            writer.write_set_project_roots([debugger_unittest._get_debugger_test_file('my_code')])
            json_facade.write_launch(debugOptions=['Django'])
            json_facade.write_set_exception_breakpoints(['raised'])
        else:
            json_facade.write_launch(debugOptions=['DebugStdLib', 'Django'])
            # Don't set to all 'raised' because we'd stop on standard library exceptions here
            # (which is not something we want).
            json_facade.write_set_exception_breakpoints(exception_options=[
                ExceptionOptions(breakMode='always', path=[
                    {'names': ['Python Exceptions']},
                    {'names': ['AssertionError']},
                ])
            ])

        writer.write_make_initial_run()

        t = writer.create_request_thread('my_app/template_error')
        time.sleep(5)  # Give django some time to get to startup before requesting the page
        t.start()

        hit = writer.wait_for_breakpoint_hit(REASON_CAUGHT_EXCEPTION, line=7, file='template_error.html')

        stack_trace_request = json_facade.write_request(
            pydevd_schema.StackTraceRequest(pydevd_schema.StackTraceArguments(
                threadId=hit.thread_id,
                format={'module': True, 'line': True}
        )))
        stack_trace_response = json_facade.wait_for_response(stack_trace_request)
        stack_trace_response_body = stack_trace_response.body
        stack_frame = next(iter(stack_trace_response_body.stackFrames))
        assert stack_frame['source']['path'].endswith('template_error.html')

        json_hit = json_facade.get_stack_as_json_hit(hit.thread_id)
        variables_response = json_facade.get_variables_response(json_hit.frameId)
        entries = [x for x in variables_response.to_dict()['body']['variables'] if x['name'] == 'entry']
        assert len(entries) == 1
        variables_response = json_facade.get_variables_response(entries[0]['variablesReference'])
        assert variables_response.to_dict()['body']['variables'] == [
            {'name': 'key', 'value': "'v1'", 'type': 'str', 'evaluateName': 'entry.key', 'presentationHint': {'attributes': ['rawString']}},
            {'name': 'val', 'value': "'v1'", 'type': 'str', 'evaluateName': 'entry.val', 'presentationHint': {'attributes': ['rawString']}}
        ]

        writer.write_run_thread(hit.thread_id)
        writer.finished_ok = True


@pytest.mark.skipif(not TEST_FLASK, reason='No flask available')
@pytest.mark.parametrize("jmc", [False, True])
def test_case_flask_exceptions(case_setup_flask, jmc):
    with case_setup_flask.test_file(EXPECTED_RETURNCODE='any') as writer:
        json_facade = JsonFacade(writer)
        writer.write_set_protocol('http_json')

        if jmc:
            writer.write_set_project_roots([debugger_unittest._get_debugger_test_file('my_code')])
            json_facade.write_launch(debugOptions=['Jinja'])
            json_facade.write_set_exception_breakpoints(['raised'])
        else:
            json_facade.write_launch(debugOptions=['DebugStdLib', 'Jinja'])
            # Don't set to all 'raised' because we'd stop on standard library exceptions here
            # (which is not something we want).
            json_facade.write_set_exception_breakpoints(exception_options=[
                ExceptionOptions(breakMode='always', path=[
                    {'names': ['Python Exceptions']},
                    {'names': ['IndexError']},
                ])
            ])
        writer.write_make_initial_run()

        t = writer.create_request_thread('/bad_template')
        time.sleep(2)  # Give flask some time to get to startup before requesting the page
        t.start()

        hit = writer.wait_for_breakpoint_hit(REASON_CAUGHT_EXCEPTION, line=8, file='bad.html')
        writer.write_run_thread(hit.thread_id)

        writer.finished_ok = True


@pytest.mark.skipif(IS_APPVEYOR or IS_JYTHON, reason='Flaky on appveyor / Jython encoding issues (needs investigation).')
def test_redirect_output(case_setup):

    def get_environ(writer):
        env = os.environ.copy()

        env["PYTHONIOENCODING"] = 'utf-8'
        return env

    with case_setup.test_file('_debugger_case_redirect.py', get_environ=get_environ) as writer:
        original_ignore_stderr_line = writer._ignore_stderr_line
        writer.write_set_protocol('http_json')
        json_facade = JsonFacade(writer)

        @overrides(writer._ignore_stderr_line)
        def _ignore_stderr_line(line):
            if original_ignore_stderr_line(line):
                return True
            return line.startswith((
                'text',
                'binary',
                'a'
            ))

        writer._ignore_stderr_line = _ignore_stderr_line

        # Note: writes to stdout and stderr are now synchronous (so, the order
        # must always be consistent and there's a message for each write).
        expected = [
            'text\n',
            'binary or text\n',
            'ação1\n',
        ]

        if sys.version_info[0] >= 3:
            expected.extend((
                'binary\n',
                'ação2\n'.encode(encoding='latin1').decode('utf-8', 'replace'),
                'ação3\n',
            ))

        new_expected = [(x, 'stdout') for x in expected]
        new_expected.extend([(x, 'stderr') for x in expected])

        writer.write_start_redirect()

        writer.write_make_initial_run()
        msgs = []
        ignored = []
        while len(msgs) < len(new_expected):
            try:
                output_event = json_facade.wait_for_json_message(OutputEvent)
                output = output_event.body.output
                category = output_event.body.category
                if IS_PY2:
                    if isinstance(output, unicode):
                        output = output.encode('utf-8')
                    if isinstance(category, unicode):
                        category = category.encode('utf-8')
                msg = (output, category)
            except Exception:
                for msg in msgs:
                    sys.stderr.write('Found: %s\n' % (msg,))
                for msg in new_expected:
                    sys.stderr.write('Expected: %s\n' % (msg,))
                for msg in ignored:
                    sys.stderr.write('Ignored: %s\n' % (msg,))
                raise
            if msg not in new_expected:
                ignored.append(msg)
                continue
            msgs.append(msg)

        if msgs != new_expected:
            print(msgs)
            print(new_expected)
        assert msgs == new_expected
        writer.finished_ok = True


if __name__ == '__main__':
    pytest.main(['-k', 'test_case_skipping_filters', '-s'])

