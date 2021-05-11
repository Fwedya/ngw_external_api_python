# -*- coding: utf-8 -*-

import os
import sys


COMPAT_PY_UNSUPPORTED_MSG = 'Unsupported Python version'


COMPAT_PY_VERSION = None
if sys.version_info[0] == 2:
    COMPAT_PY_VERSION = 2
elif sys.version_info[0] == 3:
    COMPAT_PY_VERSION = 3


if COMPAT_PY_VERSION == 2:
    #import urllib
    from urllib import unquote_plus
    from urlparse import urlparse
    from urlparse import parse_qs

elif COMPAT_PY_VERSION == 3:
    #import urllib.request, urllib.parse, urllib.error
    from urllib.parse import unquote_plus
    from urllib.parse import urlparse
    from urllib.parse import parse_qs

else:
    raise NotImplementedError(COMPAT_PY_UNSUPPORTED_MSG)


class CompatPy:

    @classmethod
    def get_dirname(cls, dpath):
        if COMPAT_PY_VERSION == 2:
            return os.path.dirname(dpath).decode(sys.getfilesystemencoding())
        elif COMPAT_PY_VERSION == 3:
            return os.path.dirname(dpath)
        else:
            raise NotImplementedError(COMPAT_PY_UNSUPPORTED_MSG)



