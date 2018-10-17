# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

import os.path
import pytest

from ..helpers.pattern import ANY
from ..helpers.timeline import Event
from .testfiles.testroots import get_test_root
from ..helpers.webhelper import get_url_from_str, get_web_content

DJANGO1_ROOT = get_test_root('django1')
DJANGO1_MANAGE = os.path.join(DJANGO1_ROOT, 'app.py')
DJANGO1_TEMPLATE = os.path.join(DJANGO1_ROOT, 'templates', 'hello.html')

def _wait_for_django_link(debug_session):
    o = None
    while True:
        if o:
            o = debug_session.wait_for_next(o >> Event('output'))
        else:
            o = debug_session.wait_for_next(Event('output'))
        for e in debug_session.all_occurrences_of(Event('output')):
            link = get_url_from_str(o.body['output'])
            if link is not None:
                return link


def _django_no_multiproc_common(debug_session):
    debug_session.multiprocess = False
    debug_session.cli_args = ['runserver', '--noreload', '--nothreading']

    debug_session.ignore_unobserved += [
        # The queue module can spawn helper background threads, depending on Python version
        # and platform. Since this is an implementation detail, we don't care about those.
        Event('thread', ANY.dict_with({'reason': 'started'})),
        Event('module')
    ]

    debug_session.debug_options = ['RedirectOutput', 'Django']
    debug_session.cwd = DJANGO1_ROOT
    debug_session.expected_returncode = ANY  # No clean way to kill Django server

@pytest.mark.parametrize('bp_file, bp_line, bp_name', [
  (DJANGO1_MANAGE, 40, 'home'),
  (DJANGO1_TEMPLATE, 8, 'Django Template'),
])
def test_django_breakpoint_no_multiproc(debug_session, bp_file, bp_line, bp_name):
    _django_no_multiproc_common(debug_session)
    debug_session.prepare_to_run(filename=DJANGO1_MANAGE)

    bp_var_content = 'Django-Django-Test'
    debug_session.send_request('setBreakpoints', arguments={
        'source': {'path': bp_file},
        'breakpoints': [{'line': bp_line}, ],
    }).wait_for_response()

    debug_session.start_debugging()

    link = _wait_for_django_link(debug_session)
    assert link is not None

    # connect to web server
    with get_web_content(link, {}) as web_result:
        thread_stopped = debug_session.wait_for_next(Event('stopped', ANY.dict_with({'reason': 'breakpoint'})))
        assert thread_stopped.body['threadId'] is not None

        tid = thread_stopped.body['threadId']

        resp_stacktrace = debug_session.send_request('stackTrace', arguments={
            'threadId': tid,
        }).wait_for_response()
        assert resp_stacktrace.body['totalFrames'] > 1
        frames = resp_stacktrace.body['stackFrames']
        assert frames[0] == {
            'id': 1,
            'name': bp_name,
            'source': {
                'sourceReference': ANY,
                'path': bp_file,
            },
            'line': bp_line,
            'column': 1,
        }

        fid = frames[0]['id']
        resp_scopes = debug_session.send_request('scopes', arguments={
            'frameId': fid
        }).wait_for_response()
        scopes = resp_scopes.body['scopes']
        assert len(scopes) > 0

        resp_variables = debug_session.send_request('variables', arguments={
            'variablesReference': scopes[0]['variablesReference']
        }).wait_for_response()
        variables = list(v for v in resp_variables.body['variables'] if v['name'] == 'content')
        assert variables == [{
                'name': 'content',
                'type': 'str',
                'value': repr(bp_var_content),
                'presentationHint': {'attributes': ['rawString']},
                'evaluateName': 'content'
            }]

        debug_session.send_request('continue').wait_for_response()
        debug_session.wait_for_next(Event('continued'))

    assert web_result['content'].find(bp_var_content) != -1

    # shutdown to web server
    link += 'exit' if link.endswith('/') else '/exit'
    with get_web_content(link):
        pass

@pytest.mark.parametrize('ex_type, ex_line', [
  ('handled', 50),
  ('unhandled', 64),
])
def test_django_exception_no_multiproc(debug_session, ex_type, ex_line):
    _django_no_multiproc_common(debug_session)
    debug_session.prepare_to_run(filename=DJANGO1_MANAGE)

    debug_session.send_request('setExceptionBreakpoints', arguments={
        'filters': ['raised', 'uncaught'],
    }).wait_for_response()

    debug_session.start_debugging()

    base_link = _wait_for_django_link(debug_session)
    assert base_link is not None

    link = base_link + ex_type if base_link.endswith('/') else ('/' + ex_type)
    with get_web_content(link, {}):
        thread_stopped = debug_session.wait_for_next(Event('stopped', ANY.dict_with({'reason': 'exception'})))
        assert thread_stopped == Event('stopped', ANY.dict_with({
            'reason': 'exception',
            'text': 'ArithmeticError',
            'description': 'Hello'
        }))

        tid = thread_stopped.body['threadId']
        resp_exception_info = debug_session.send_request(
            'exceptionInfo',
            arguments={'threadId': tid, }
        ).wait_for_response()
        exception = resp_exception_info.body
        assert exception == {
            'exceptionId': 'ArithmeticError',
            'breakMode': 'always',
            'description': 'Hello',
            'details': {
                'message': 'Hello',
                'typeName': 'ArithmeticError',
                'source': DJANGO1_MANAGE,
                'stackTrace': ANY,
            }
        }

        resp_stacktrace = debug_session.send_request('stackTrace', arguments={
            'threadId': tid,
        }).wait_for_response()
        assert resp_stacktrace.body['totalFrames'] > 1
        frames = resp_stacktrace.body['stackFrames']
        assert frames[0] == {
            'id': ANY,
            'name': 'bad_route_' + ex_type,
            'source': {
                'sourceReference': ANY,
                'path': DJANGO1_MANAGE,
            },
            'line': ex_line,
            'column': 1,
        }

        debug_session.send_request('continue').wait_for_response()
        debug_session.wait_for_next(Event('continued'))

    # shutdown to web server
    link = base_link + 'exit' if base_link.endswith('/') else '/exit'
    with get_web_content(link):
        pass
