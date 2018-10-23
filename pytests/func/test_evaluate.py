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