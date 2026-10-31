"""Continuity daemon — local-first Android/Linux continuity backend.

Layering (each layer only imports the ones above it):

    frames      length-prefixed framing
    protocol    envelope + message validation
    identity    per-device certificate and signing key
    trust       pinned peer fingerprints
    sas         short authentication string for pairing
    session     TLS transport + authenticated peer session
    discovery   mDNS advertisement/browsing
    services    clipboard, files, notifications, dex, diagnostics
    core        device state, event bus, feature dispatch
    ipc         local JSON-lines socket for every UI
    daemon      process wiring
    cli         continuityctl
"""

__version__ = "0.1.0"
PROTOCOL_VERSION = 2
APP_NAME = "continuity"
