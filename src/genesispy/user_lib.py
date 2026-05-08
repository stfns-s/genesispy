"""User-extensible mixin -- the Python port of ``Genesis2::MyLib``.

In the original Perl flow, users could push ``MyLib`` onto
``@Genesis2::UniqueModule::ISA`` to inject helper methods into every
generated module.  In Python we expose the same hook as a mixin class:
subclass :class:`UserMixin` and the elaboration engine will mix it into
each generated module's MRO.
"""

from __future__ import annotations


class UserMixin:
    """Empty base mixin -- subclass to inject methods into all generated modules.

    Generated module classes inherit ``(UniqueModule, UserMixin)`` so any
    method defined on a ``UserMixin`` subclass becomes callable from
    inside templates as ``self.<method>()``.
    """

    pass
