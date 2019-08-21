from __future__ import print_function
import dis
from _pydev_imps._pydev_saved_modules import threading, thread
from _pydevd_bundle.pydevd_comm import GlobalDebuggerHolder
from _pydevd_frame_eval.pydevd_frame_tracing import create_pydev_trace_code_wrapper, update_globals_dict, dummy_tracing_holder
from _pydevd_frame_eval.pydevd_modify_bytecode import insert_code
from pydevd_file_utils import get_abs_path_real_path_and_base_from_file, NORM_PATHS_AND_BASE_CONTAINER
from _pydevd_bundle.pydevd_trace_dispatch import fix_top_level_trace_and_get_trace_func

from _pydevd_bundle.pydevd_additional_thread_info import _set_additional_thread_info_lock
from _pydevd_bundle.pydevd_cython cimport PyDBAdditionalThreadInfo


_thread_local_info = threading.local()

def clear_thread_local_info():
    global _thread_local_info
    _thread_local_info = threading.local()


cdef class ThreadInfo:

    cdef public PyDBAdditionalThreadInfo additional_info
    cdef public bint is_pydevd_thread
    cdef public int inside_frame_eval
    cdef public bint fully_initialized
    cdef public object thread_trace_func

    def __init__(self):
        self.additional_info = None
        self.is_pydevd_thread = False
        self.inside_frame_eval = 0
        self.fully_initialized = False
        self.thread_trace_func = None
        
    def initialize_if_possible(self):
        # Don't call threading.currentThread because if we're too early in the process
        # we may create a dummy thread.
        self.inside_frame_eval += 1

        try:
            thread_ident = threading.get_ident()  # Note this is py3 only, if py2 needed to be supported, _get_ident would be needed.
            t = threading._active.get(thread_ident)
            if t is None:
                return  # Cannot initialize until thread becomes active.

            if getattr(t, 'is_pydev_daemon_thread', False):
                self.is_pydevd_thread = True
                self.fully_initialized = True
            else:
                try:
                    additional_info = t.additional_info
                    if additional_info is None:
                        raise AttributeError()
                except:
                    with _set_additional_thread_info_lock:
                        # If it's not there, set it within a lock to avoid any racing
                        # conditions.
                        additional_info = getattr(thread, 'additional_info', None)
                        if additional_info is None:
                            additional_info = PyDBAdditionalThreadInfo()
                        t.additional_info = additional_info
                self.additional_info = additional_info
                self.fully_initialized = True
        finally:
            self.inside_frame_eval -= 1


cdef class FuncCodeInfo:

    cdef public str co_filename
    cdef public str real_path
    cdef bint always_skip_code
    cdef public bint breakpoint_found
    cdef public object new_code
    
    # When breakpoints_mtime != PyDb.mtime the validity of breakpoints have
    # to be re-evaluated (if invalid a new FuncCodeInfo must be created and
    # tracing can't be disabled for the related frames).
    cdef public int breakpoints_mtime

    def __init__(self):
        self.co_filename = ''
        self.real_path = ''
        self.always_skip_code = False

        # If breakpoints are found but new_code is None,
        # this means we weren't able to actually add the code
        # where needed, so, fallback to tracing.
        self.breakpoint_found = False
        self.new_code = None
        self.breakpoints_mtime = -1


def dummy_trace_dispatch(frame, str event, arg):
    if event == 'call':
        if frame.f_trace is not None:
            return frame.f_trace(frame, event, arg)
    return None


def get_thread_info_py() -> ThreadInfo:
    return get_thread_info()


cdef ThreadInfo get_thread_info():
    '''
    Provides thread-related info.

    May return None if the thread is still not active.
    '''
    cdef ThreadInfo thread_info
    try:
        # Note: changing to a `dict[thread.ident] = thread_info` had almost no
        # effect in the performance.
        thread_info = _thread_local_info.thread_info
    except:
        thread_info = ThreadInfo()
        thread_info.inside_frame_eval += 1
        try:
            _thread_local_info.thread_info = thread_info

            # Note: _code_extra_index is not actually thread-related,
            # but this is a good point to initialize it.    
            global _code_extra_index
            if _code_extra_index == -1:
                _code_extra_index = _PyEval_RequestCodeExtraIndex(release_co_extra)
                
            thread_info.initialize_if_possible()
        finally:
            thread_info.inside_frame_eval -= 1

    return thread_info


def decref_py(obj):
    '''
    Helper to be called from Python.
    '''
    Py_DECREF(obj)


def get_func_code_info_py(frame, code_obj) -> FuncCodeInfo:
    '''
    Helper to be called from Python.
    '''
    return get_func_code_info(<PyFrameObject *> frame, <PyCodeObject *> code_obj)


_code_extra_index: Py_SIZE = -1

cdef FuncCodeInfo get_func_code_info(PyFrameObject * frame_obj, PyCodeObject * code_obj):
    '''
    Provides code-object related info.

    Stores the gathered info in a cache in the code object itself. Note that
    multiple threads can get the same info.

    get_thread_info() *must* be called at least once before get_func_code_info()
    to initialize _code_extra_index.
    '''
    # f_code = <object> code_obj
    # DEBUG = f_code.co_filename.endswith('_debugger_case_multiprocessing.py')
    # if DEBUG:
    #     print('get_func_code_info', f_code.co_name, f_code.co_filename)

    cdef object main_debugger = GlobalDebuggerHolder.global_dbg
    
    cdef PyObject * extra
    _PyCode_GetExtra(<PyObject *> code_obj, _code_extra_index, & extra)
    if extra is not NULL:
        extra_obj = <PyObject *> extra
        if extra_obj is not NULL:
            func_code_info_obj = <FuncCodeInfo> extra_obj
            if func_code_info_obj.breakpoints_mtime == main_debugger.mtime:
                # if DEBUG:
                #     print('get_func_code_info: matched mtime', f_code.co_name, f_code.co_filename)

                return func_code_info_obj

    cdef str co_filename = <str> code_obj.co_filename
    cdef str co_name = <str> code_obj.co_name
    cdef set break_at_lines
    cdef dict cache_file_type
    cdef tuple cache_file_type_key

    func_code_info = FuncCodeInfo()
    func_code_info.breakpoints_mtime = main_debugger.mtime

    func_code_info.co_filename = co_filename

    if not func_code_info.always_skip_code:
        try:
            abs_path_real_path_and_base = NORM_PATHS_AND_BASE_CONTAINER[co_filename]
        except:
            abs_path_real_path_and_base = get_abs_path_real_path_and_base_from_file(co_filename)

        func_code_info.real_path = abs_path_real_path_and_base[1]
        
        cache_file_type = main_debugger.get_cache_file_type()
        # Note: this cache key must be the same from PyDB.get_file_type() -- see it for comments
        # on the cache.
        cache_file_type_key = (frame_obj.f_code.co_firstlineno, abs_path_real_path_and_base[0], <object>frame_obj.f_code)
        try:
            file_type = cache_file_type[cache_file_type_key]  # Make it faster
        except:
            file_type = main_debugger.get_file_type(<object>frame_obj, abs_path_real_path_and_base)  # we don't want to debug anything related to pydevd

        if file_type is not None:
            func_code_info.always_skip_code = True

    if not func_code_info.always_skip_code:
        was_break: bool = False
        if main_debugger is not None:
            breakpoints: dict = main_debugger.breakpoints.get(func_code_info.real_path)
            # print('\n---')
            # print(main_debugger.breakpoints)
            # print(func_code_info.real_path)
            # print(main_debugger.breakpoints.get(func_code_info.real_path))
            code_obj_py: object = <object> code_obj
            if breakpoints:
                # if DEBUG:
                #    print('found breakpoints', code_obj_py.co_name, breakpoints)
                break_at_lines = set()
                new_code = None
                for offset, line in dis.findlinestarts(code_obj_py):
                    if line in breakpoints:
                        # breakpoint = breakpoints[line]
                        # if DEBUG:
                        #    print('created breakpoint', code_obj_py.co_name, line)
                        func_code_info.breakpoint_found = True
                        break_at_lines.add(line)
    
                        success, new_code = insert_code(
                            code_obj_py, create_pydev_trace_code_wrapper(line), line, tuple(break_at_lines))
                        code_obj_py = new_code
    
                        if not success:
                            func_code_info.new_code = None
                            break
                else:
                    # Ok, all succeeded, set to generated code object.
                    func_code_info.new_code = new_code
                    

    Py_INCREF(func_code_info)
    _PyCode_SetExtra(<PyObject *> code_obj, _code_extra_index, <PyObject *> func_code_info)

    return func_code_info


cdef PyObject * get_bytecode_while_frame_eval(PyFrameObject * frame_obj, int exc):
    '''
    This function makes the actual evaluation and changes the bytecode to a version
    where programmatic breakpoints are added.
    '''
    if GlobalDebuggerHolder is None or _thread_local_info is None or exc:
        # Sometimes during process shutdown these global variables become None
        return _PyEval_EvalFrameDefault(frame_obj, exc)

    # co_filename: str = <str>frame_obj.f_code.co_filename
    # if co_filename.endswith('threading.py'):
    #     return _PyEval_EvalFrameDefault(frame_obj, exc)

    cdef ThreadInfo thread_info
    cdef int STATE_SUSPEND = 2
    cdef int CMD_STEP_INTO = 107
    cdef int CMD_STEP_OVER = 108
    cdef int CMD_STEP_OVER_MY_CODE = 159
    cdef int CMD_STEP_INTO_MY_CODE = 144
    cdef bint can_skip = True
    try:
        thread_info = _thread_local_info.thread_info
    except:
        thread_info = get_thread_info()
        if thread_info is None:
            return _PyEval_EvalFrameDefault(frame_obj, exc)

    if thread_info.inside_frame_eval:
        return _PyEval_EvalFrameDefault(frame_obj, exc)
    
    if not thread_info.fully_initialized:
        thread_info.initialize_if_possible()
        if not thread_info.fully_initialized:
            return _PyEval_EvalFrameDefault(frame_obj, exc)

    # Can only get additional_info when fully initialized.            
    cdef PyDBAdditionalThreadInfo additional_info = thread_info.additional_info
    if thread_info.is_pydevd_thread or additional_info.is_tracing:
        # Make sure that we don't trace pydevd threads or inside our own calls.
        return _PyEval_EvalFrameDefault(frame_obj, exc)

    # frame = <object> frame_obj
    # DEBUG = frame.f_code.co_filename.endswith('_debugger_case_tracing.py')
    # if DEBUG:
    #     print('get_bytecode_while_frame_eval', frame.f_lineno, frame.f_code.co_name, frame.f_code.co_filename)
    
    thread_info.inside_frame_eval += 1
    additional_info.is_tracing = True
    try:
        main_debugger: object = GlobalDebuggerHolder.global_dbg
        if main_debugger is None:
            return _PyEval_EvalFrameDefault(frame_obj, exc)
        frame = <object> frame_obj
        
        if thread_info.thread_trace_func is None:
            trace_func, apply_to_global = fix_top_level_trace_and_get_trace_func(main_debugger, frame)
            if apply_to_global:
                thread_info.thread_trace_func = trace_func
                
        if additional_info.pydev_step_cmd in (CMD_STEP_INTO, CMD_STEP_INTO_MY_CODE) or \
                main_debugger.break_on_caught_exceptions or \
                main_debugger.has_plugin_exception_breaks or \
                main_debugger.signature_factory or \
                additional_info.pydev_step_cmd in (CMD_STEP_OVER, CMD_STEP_OVER_MY_CODE) and main_debugger.show_return_values and frame.f_back is additional_info.pydev_step_stop:
            
            # if DEBUG:
            #     print('get_bytecode_while_frame_eval enabled trace')
            if thread_info.thread_trace_func is not None:
                frame.f_trace = thread_info.thread_trace_func
            else:
                frame.f_trace = <object> main_debugger.trace_dispatch
        else:
            func_code_info: FuncCodeInfo = get_func_code_info(frame_obj, frame_obj.f_code)
            # if DEBUG:
            #     print('get_bytecode_while_frame_eval always skip', func_code_info.always_skip_code)
            if not func_code_info.always_skip_code:
    
                if main_debugger.has_plugin_line_breaks or main_debugger.has_plugin_exception_breaks:
                    can_skip = main_debugger.plugin.can_skip(main_debugger, <object> frame_obj)

                    if not can_skip:
                        # if DEBUG:
                        #     print('get_bytecode_while_frame_eval not can_skip')
                        if thread_info.thread_trace_func is not None:
                            frame.f_trace = thread_info.thread_trace_func
                        else:
                            frame.f_trace = <object> main_debugger.trace_dispatch
                            
                if can_skip and func_code_info.breakpoint_found:
                    # if DEBUG:
                    #     print('get_bytecode_while_frame_eval new_code', func_code_info.new_code)

                    # If breakpoints are found but new_code is None,
                    # this means we weren't able to actually add the code
                    # where needed, so, fallback to tracing.
                    if func_code_info.new_code is None:
                        if thread_info.thread_trace_func is not None:
                            frame.f_trace = thread_info.thread_trace_func
                        else:
                            frame.f_trace = <object> main_debugger.trace_dispatch
                    else:
                        # print('Using frame eval break for', <object> frame_obj.f_code.co_name)
                        update_globals_dict(<object> frame_obj.f_globals)
                        Py_INCREF(func_code_info.new_code)
                        old = <object> frame_obj.f_code
                        frame_obj.f_code = <PyCodeObject *> func_code_info.new_code
                        Py_DECREF(old)

    finally:
        thread_info.inside_frame_eval -= 1
        additional_info.is_tracing = False

    return _PyEval_EvalFrameDefault(frame_obj, exc)


def frame_eval_func():
    cdef PyThreadState *state = PyThreadState_Get()
    state.interp.eval_frame = get_bytecode_while_frame_eval
    global dummy_tracing_holder
    dummy_tracing_holder.set_trace_func(dummy_trace_dispatch)


def stop_frame_eval():
    cdef PyThreadState *state = PyThreadState_Get()
    state.interp.eval_frame = _PyEval_EvalFrameDefault
