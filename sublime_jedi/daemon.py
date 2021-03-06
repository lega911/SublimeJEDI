# -*- coding: utf-8 -*-
from concurrent.futures import ThreadPoolExecutor, TimeoutError

from functools import wraps
from collections import defaultdict
import time
import os

import jedi
from jedi.api import environment

import sublime

from .facade import JediFacade
from .console_logging import getLogger
from .utils import get_settings
import pydef


logger = getLogger(__name__)

DAEMONS = defaultdict(dict)  # per window
REQUESTORS = defaultdict(dict)  # per window


def _prepare_request_data(view, location):
    if location is None:
        location = view.sel()[0].begin()
    current_line, current_column = view.rowcol(location)

    filename = view.file_name() or ''
    source = view.substr(sublime.Region(0, view.size()))
    return filename, source, current_line, current_column


def _get_daemon(view):
    window_id = view.window().id()
    if window_id not in DAEMONS:
        DAEMONS[window_id] = Daemon(settings=get_settings(view))
    return DAEMONS[window_id]


def _get_requestor(view):
    window_id = view.window().id()
    if window_id not in REQUESTORS:
        REQUESTORS[window_id] = ThreadPoolExecutor(max_workers=1)
    return REQUESTORS[window_id]


def ask_daemon_sync(view, ask_type, ask_kwargs, location=None):
    """Jedi sync request shortcut.

    :type view: sublime.View
    :type ask_type: str
    :type ask_kwargs: dict or None
    :type location: type of (int, int) or None
    """
    daemon = _get_daemon(view)
    return daemon.request(
        ask_type,
        ask_kwargs or {},
        *_prepare_request_data(view, location))


def ask_daemon_with_timeout(
        view,
        ask_type,
        ask_kwargs=None,
        location=None,
        timeout=3):
    """Jedi sync request shortcut with timeout.

    :type view: sublime.View
    :type ask_type: str
    :type ask_kwargs: dict or None
    :type location: type of (int, int) or None
    :type timeout: int
    """
    daemon = _get_daemon(view)
    requestor = _get_requestor(view)
    request_data = _prepare_request_data(view, location)

    def _target():
        return daemon.request(ask_type, ask_kwargs or {}, *request_data)

    request = requestor.submit(_target)
    try:
        return request.result(timeout=timeout)
    except TimeoutError:
        # no need to wait more
        request.cancel()
        raise


def ask_daemon(view, callback, ask_type, ask_kwargs=None, location=None):
    """Jedi async request shortcut.

    :type view: sublime.View
    :type callback: callable
    :type ask_type: str
    :type ask_kwargs: dict or None
    :type location: type of (int, int) or None
    """
    window_id = view.window().id()

    def _async_summon():
        answer = ask_daemon_sync(view, ask_type, ask_kwargs, location)
        run_in_active_view(window_id)(callback)(answer)

    if callback:
        sublime.set_timeout_async(_async_summon, 0)


def run_in_active_view(window_id):
    """Run function in active ST active view for binded window.

    sublime.View instance would be passed as first parameter to function.
    """
    def _decorator(func):
        @wraps(func)
        def _wrapper(*args, **kwargs):
            for window in sublime.windows():
                if window.id() == window_id:
                    return func(window.active_view(), *args, **kwargs)

            logger.info(
                'Unable to find a window where function must be called.'
            )
        return _wrapper
    return _decorator


class Daemon:
    """Jedi Requester."""

    def __init__(self, settings):
        """Prepare to call daemon.

        :type settings: dict
        """
        python_virtualenv = settings.get('python_virtualenv')
        python_interpreter = settings.get('python_interpreter')

        logger.debug('Jedi Environment: {0}'.format(
            (python_virtualenv, python_interpreter))
        )

        if python_virtualenv:
            self.env = environment.create_environment(python_virtualenv,
                                                      safe=False)
        elif python_interpreter:
            self.env = environment.Environment(
                environment._get_python_prefix(python_interpreter),
                python_interpreter
            )
        else:
            self.env = jedi.get_default_environment()

        self.sys_path = self.env.get_sys_path()
        # prepare the extra packages if any
        extra_packages = settings.get('extra_packages')
        if extra_packages:
            self.sys_path = extra_packages + self.sys_path

        # how to autocomplete arguments
        self.complete_funcargs = settings.get('complete_funcargs')
        self.pydef = settings.get('pydef')

    def request(
            self,
            request_type,
            request_kwargs,
            filename,
            source,
            line,
            column):
        """Send request to daemon process."""

        logger.info('Sending request to daemon for "{0}"'.format(request_type))
        logger.debug((request_type, request_kwargs, filename, line, column))

        pydef_log = self.pydef and self.pydef.get('log')
        path = self.sys_path
        if self.pydef and self.pydef.get('auto_path'):
            curdir = os.path.dirname(filename)
            if not os.path.isfile(os.path.join(curdir, '__init__.py')) and curdir not in path:
                path = [curdir] + path
                if pydef_log:
                    print('+path', curdir)

        answer = None
        start = time.time()
        if request_type in ('goto', 'pydef_goto') and self.pydef:
            try:
                if pydef_log:
                    print('pydef {}'.format(dict(
                        request_type=request_type,
                        path=path,
                        filename=filename,
                        row=line,
                        col=column
                    )))
                result = pydef.goto_definition(
                    path=path,
                    filename=filename,
                    row=line,
                    col=column,
                    source=source
                )
                if pydef_log:
                    print('pydef ({:.3f}s) {}'.format(time.time() - start, result))
                if result:
                    answer = [(result.filename, result.row + 1, 0)]
            except Exception:
                import traceback
                traceback.print_exc()
            if self.pydef.get('skip_jedi') or request_type == 'pydef_goto':
                return answer
        if not answer:
            facade = JediFacade(
                env=self.env,
                complete_funcargs=self.complete_funcargs,
                source=source,
                line=line + 1,
                column=column,
                filename=filename,
                sys_path=path,
            )

            answer = facade.get(request_type, request_kwargs)

        logger.debug('Answer ({:.3f}s): {}'.format(time.time() - start, answer))

        return answer
