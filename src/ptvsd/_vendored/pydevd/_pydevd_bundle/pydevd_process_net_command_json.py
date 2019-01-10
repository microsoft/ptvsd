from _pydevd_bundle._debug_adapter import pydevd_base_schema
import json
from _pydevd_bundle.pydevd_api import PyDevdAPI
from _pydevd_bundle.pydevd_comm_constants import CMD_RETURN
from _pydevd_bundle.pydevd_net_command import NetCommand


class _PyDevJsonCommandProcessor(object):

    def __init__(self, from_json):
        self.from_json = from_json
        self.api = PyDevdAPI()

    def process_net_command_json(self, py_db, json_contents):
        '''
        Processes a debug adapter protocol json command.
        '''

        DEBUG = False

        request = self.from_json(json_contents)

        if DEBUG:
            print('Process %s: %s\n' % (
                request.__class__.__name__, json.dumps(request.to_dict(), indent=4, sort_keys=True),))

        assert request.type == 'request'
        method_name = 'on_%s_request' % (request.command.lower(),)
        on_request = getattr(self, method_name, None)
        if on_request is None:
            print('Unhandled: %s not available in _PyDevJsonCommandProcessor.\n' % (method_name,))
            return

        if DEBUG:
            print('Handled in pydevd: %s (in _PyDevJsonCommandProcessor).\n' % (method_name,))

        py_db._main_lock.acquire()
        try:

            cmd = on_request(py_db, request)
            if cmd is not None:
                py_db.writer.add_command(cmd)
        finally:
            py_db._main_lock.release()

    def on_configurationdone_request(self, py_db, request):
        '''
        :param ConfigurationDoneRequest request:
        '''
        self.api.run(py_db)
        configuration_done_response = pydevd_base_schema.build_response(request)
        return NetCommand(CMD_RETURN, 0, configuration_done_response.to_dict(), is_json=True)

    def on_threads_request(self, py_db, request):
        '''
        :param ThreadsRequest request:
        '''
        return self.api.list_threads(py_db, request.seq)

    def on_completions_request(self, py_db, request):
        '''
        :param CompletionsRequest request:
        '''
        arguments = request.arguments  # : :type arguments: CompletionsArguments
        seq = request.seq
        text = arguments.text
        thread_id, frame_id = arguments.frameId

        # Note: line and column are 1-based (convert to 0-based for pydevd).
        column = arguments.column - 1

        if arguments.line is None:
            # line is optional
            line = -1
        else:
            line = arguments.line - 1

        self.api.request_completions(py_db, seq, thread_id, frame_id, text, line=line, column=column)


process_net_command_json = _PyDevJsonCommandProcessor(pydevd_base_schema.from_json).process_net_command_json
