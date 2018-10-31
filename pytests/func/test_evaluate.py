# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

import pytest

from pytests.helpers import print
from pytests.helpers.pattern import ANY
from pytests.helpers.timeline import Event


def _common_setup(debug_session, path, run_as):
    debug_session.ignore_unobserved += [
        Event('thread', ANY.dict_with({'reason': 'started'})),
        Event('module')
    ]
    if run_as == 'file':
        debug_session.prepare_to_run(filename=path)
    elif run_as == 'module':
        debug_session.add_file_to_pythonpath(path)
        debug_session.prepare_to_run(module='code_to_debug')
    elif run_as == 'code':
        with open(path, 'r') as f:
            code = f.read()
        debug_session.prepare_to_run(code=code)
    else:
        pytest.fail()


@pytest.mark.parametrize('run_as', ['file', 'module'])
def test_variables_and_evaluate(debug_session, pyfile, run_as):
    @pyfile
    def code_to_debug():
        a = 1
        b = {"one": 1, "two": 2}
        c = 3
        print([a, b, c])
    bp_line = 4
    bp_file = code_to_debug
    _common_setup(debug_session, bp_file, run_as)

    debug_session.send_request('setBreakpoints', arguments={
        'source': {'path': bp_file},
        'breakpoints': [{'line': bp_line}, ],
    }).wait_for_response()
    debug_session.start_debugging()

    thread_stopped = debug_session.wait_for_next(Event('stopped'), ANY.dict_with({'reason': 'breakpoint'}))
    assert thread_stopped.body['threadId'] is not None

    tid = thread_stopped.body['threadId']

    resp_stacktrace = debug_session.send_request('stackTrace', arguments={
        'threadId': tid,
    }).wait_for_response()
    assert resp_stacktrace.body['totalFrames'] > 0
    frames = resp_stacktrace.body['stackFrames']

    fid = frames[0]['id']
    resp_scopes = debug_session.send_request('scopes', arguments={
        'frameId': fid
    }).wait_for_response()
    scopes = resp_scopes.body['scopes']
    assert len(scopes) > 0

    resp_variables = debug_session.send_request('variables', arguments={
        'variablesReference': scopes[0]['variablesReference']
    }).wait_for_response()
    variables = list(v for v in resp_variables.body['variables'] if v['name'] in ['a', 'b', 'c'])
    assert len(variables) == 3

    # variables should be sorted alphabetically
    assert ['a', 'b', 'c'] == list(v['name'] for v in variables)

    # get contents of 'b'
    resp_b_variables = debug_session.send_request('variables', arguments={
        'variablesReference': variables[1]['variablesReference']
    }).wait_for_response()
    b_variables = resp_b_variables.body['variables']
    assert len(b_variables) == 3
    assert b_variables[0] == {
        'type': 'int',
        'value': '1',
        'name': ANY.such_that(lambda x: x.find('one') > 0),
        'evaluateName': "b['one']"
    }
    assert b_variables[1] == {
        'type': 'int',
        'value': '2',
        'name': ANY.such_that(lambda x: x.find('two') > 0),
        'evaluateName': "b['two']"
    }
    assert b_variables[2] == {
        'type': 'int',
        'value': '2',
        'name': '__len__',
        'evaluateName': "b.__len__"
    }

    # simple variable
    resp_evaluate1 = debug_session.send_request('evaluate', arguments={
        'expression': 'a', 'frameId': fid
    }).wait_for_response()
    assert resp_evaluate1.body == ANY.dict_with({
        'type': 'int',
        'result': '1'
    })

    # dict variable
    resp_evaluate2 = debug_session.send_request('evaluate', arguments={
        'expression': 'b["one"]', 'frameId': fid
    }).wait_for_response()
    assert resp_evaluate2.body == ANY.dict_with({
        'type': 'int',
        'result': '1'
    })

    # expression evaluate
    resp_evaluate3 = debug_session.send_request('evaluate', arguments={
        'expression': 'a + b["one"]', 'frameId': fid
    }).wait_for_response()
    assert resp_evaluate3.body == ANY.dict_with({
        'type': 'int',
        'result': '2'
    })

    debug_session.send_request('continue').wait_for_response()
    debug_session.wait_for_next(Event('continued'))

    debug_session.wait_for_exit()


@pytest.mark.parametrize('run_as', ['file', 'module'])
def test_set_variable(debug_session, pyfile, run_as):
    @pyfile
    def code_to_debug():
        a = 1
        print(a)
    bp_line = 2
    bp_file = code_to_debug
    _common_setup(debug_session, bp_file, run_as)

    debug_session.send_request('setBreakpoints', arguments={
        'source': {'path': bp_file},
        'breakpoints': [{'line': bp_line}, ],
    }).wait_for_response()
    debug_session.start_debugging()

    thread_stopped = debug_session.wait_for_next(Event('stopped'), ANY.dict_with({'reason': 'breakpoint'}))
    assert thread_stopped.body['threadId'] is not None

    tid = thread_stopped.body['threadId']

    resp_stacktrace = debug_session.send_request('stackTrace', arguments={
        'threadId': tid,
    }).wait_for_response()
    assert resp_stacktrace.body['totalFrames'] > 0
    frames = resp_stacktrace.body['stackFrames']

    fid = frames[0]['id']
    resp_scopes = debug_session.send_request('scopes', arguments={
        'frameId': fid
    }).wait_for_response()
    scopes = resp_scopes.body['scopes']
    assert len(scopes) > 0

    resp_variables = debug_session.send_request('variables', arguments={
        'variablesReference': scopes[0]['variablesReference']
    }).wait_for_response()
    variables = list(v for v in resp_variables.body['variables'] if v['name'] == 'a')
    assert len(variables) == 1
    assert variables[0] == {
        'type': 'int',
        'value': '1',
        'name': 'a',
        'evaluateName': "a"
    }

    resp_set_variable = debug_session.send_request('setVariable', arguments={
        'variablesReference': scopes[0]['variablesReference'],
        'name': 'a',
        'value': '1000'
    }).wait_for_response()
    assert resp_set_variable.body == ANY.dict_with({
        'type': 'int',
        'value': '1000'
    })

    debug_session.send_request('continue').wait_for_response()
    debug_session.wait_for_next(Event('continued'))

    debug_session.wait_for_next(Event('output'))
    output = [e for e in debug_session.all_occurrences_of(Event('output'))
              if e.body['output'].startswith('1000')]
    assert any(output)

    debug_session.wait_for_exit()


@pytest.mark.parametrize('run_as', ['file', 'module'])
def test_variable_sort(debug_session, pyfile, run_as):
    @pyfile
    def code_to_debug():
        b_test = {"spam": "A", "eggs": "B", "abcd": "C"}  # noqa
        _b_test = 12  # noqa
        __b_test = 13  # noqa
        __b_test__ = 14  # noqa
        a_test = 1  # noqa
        _a_test = 2  # noqa
        __a_test = 3  # noqa
        __a_test__ = 4  # noqa
        c_test = {1: "one", 2: "two", 10: "ten"}  # noqa
        _c_test = 22  # noqa
        __c_test = 23  # noqa
        __c_test__ = 24  # noqa
        d = 3  # noqa
        print('done')

    bp_line = 13
    bp_file = code_to_debug
    _common_setup(debug_session, bp_file, run_as)

    debug_session.send_request('setBreakpoints', arguments={
        'source': {'path': bp_file},
        'breakpoints': [{'line': bp_line}, ],
    }).wait_for_response()
    debug_session.start_debugging()

    thread_stopped = debug_session.wait_for_next(Event('stopped'), ANY.dict_with({'reason': 'breakpoint'}))
    assert thread_stopped.body['threadId'] is not None

    tid = thread_stopped.body['threadId']

    resp_stacktrace = debug_session.send_request('stackTrace', arguments={
        'threadId': tid,
    }).wait_for_response()
    assert resp_stacktrace.body['totalFrames'] > 0
    frames = resp_stacktrace.body['stackFrames']

    fid = frames[0]['id']
    resp_scopes = debug_session.send_request('scopes', arguments={
        'frameId': fid
    }).wait_for_response()
    scopes = resp_scopes.body['scopes']
    assert len(scopes) > 0

    resp_variables = debug_session.send_request('variables', arguments={
        'variablesReference': scopes[0]['variablesReference']
    }).wait_for_response()
    variable_names = list(v['name'] for v in resp_variables.body['variables']
                          if v['name'].find('_test') > 0)
    assert variable_names == [
            'a_test', 'b_test', 'c_test', '_a_test', '_b_test', '_c_test',
            '__a_test', '__b_test', '__c_test', '__a_test__', '__b_test__',
            '__c_test__'
        ]

    # ensure string dict keys are sorted
    b_test_variable = list(v for v in resp_variables.body['variables'] if v['name'] == 'b_test')
    assert len(b_test_variable) == 1
    resp_dict_variables = debug_session.send_request('variables', arguments={
        'variablesReference': b_test_variable[0]['variablesReference']
    }).wait_for_response()
    variable_names = list(v['name'][1:5] for v in resp_dict_variables.body['variables'])
    assert len(variable_names) == 4
    assert variable_names[:3] == ['abcd', 'eggs', 'spam']

    # ensure numeric dict keys are sorted
    c_test_variable = list(v for v in resp_variables.body['variables'] if v['name'] == 'c_test')
    assert len(c_test_variable) == 1
    resp_dict_variables2 = debug_session.send_request('variables', arguments={
        'variablesReference': c_test_variable[0]['variablesReference']
    }).wait_for_response()
    variable_names = list(v['name'] for v in resp_dict_variables2.body['variables'])
    assert len(variable_names) == 4
    # NOTE: this is commented out due to sorting bug #213
    # assert variable_names[:3] == ['1', '2', '10']

    debug_session.send_request('continue').wait_for_response()
    debug_session.wait_for_next(Event('continued'))

    debug_session.wait_for_exit()
