# Immutable LeafOS brand assets

Files in this directory are content-addressed identity assets. Never overwrite
an existing asset in place. A visual change must receive a new filename derived
from its SHA-256 digest and a deliberate manifest update.

`program` verifies the active file's digest and byte length before writing a
README. The active file is also marked read-only on the local Windows checkout;
the digest and Git history are the portable enforcement layers.
