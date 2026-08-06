"""Verify TLS against the operating system's certificate store.

**The failure this prevents.** Python does not use the OS trust store. `httpx`,
and therefore every outbound call this app makes, verifies against `certifi` — a
fixed bundle of public certificate authorities compiled into the package. That is
correct on a clean machine and wrong on a great many real ones, because antivirus
software, VPNs and corporate proxies routinely terminate HTTPS and re-sign it
with their own root. They install that root into the OS store, where the browser
finds it and `certifi` never will.

The symptom is `certificate verify failed: unable to get local issuer
certificate` on a public API that plainly works in a browser on the same
machine — and because the calling code sees only "the request failed", it gets
reported as the upstream service being unavailable. This project hit precisely
that: the catalogue seeder reported a USDA rate limit while the real cause was a
locally re-signed certificate.

`truststore` redirects verification to the platform's own store — SChannel on
Windows, Security framework on macOS, OpenSSL's configured paths on Linux — so
the app trusts exactly what the machine trusts. That is strictly better than the
two alternatives usually reached for: disabling verification (which turns a
warning into a real vulnerability) or hand-appending a root to `cacert.pem`
(which is undone by the next `pip install`).
"""

import logging
import ssl

logger = logging.getLogger(__name__)

_injected = False


def use_system_trust_store() -> bool:
    """Route TLS verification through the OS store. Safe to call more than once.

    Returns whether the injection is in effect.

    Must run **before** the first `SSLContext` is created — once a client has
    built its context, it keeps it. That is why the entry points call this at
    import time rather than lazily on first use.
    """
    global _injected
    if _injected:
        return True

    try:
        import truststore
    except ImportError:
        # Not fatal. On a machine with no TLS interception certifi is perfectly
        # correct, and refusing to boot over a missing convenience would be a
        # worse failure than the one this guards against.
        logger.warning(
            "truststore is not installed; TLS will be verified against certifi. "
            "If outbound HTTPS fails with 'unable to get local issuer "
            "certificate', install it: pip install truststore"
        )
        return False

    truststore.inject_into_ssl()
    _injected = True
    logger.debug("TLS verification routed through the system trust store")
    return True


def system_trust_context() -> ssl.SSLContext:
    """An SSL context backed by the OS store, for a caller that wants one directly."""
    use_system_trust_store()
    return ssl.create_default_context()
