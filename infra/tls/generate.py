"""A local certificate authority, and a certificate for the issuer it signs.

Run by the `tls` service in compose.yaml before anything that needs it. The issuer serves
HTTPS because OAuth clients refuse to send credentials to a token endpoint over plain HTTP
unless its host is literally `localhost` — and the issuer's host is `keycloak.localhost`, the
one name that means the issuer both inside the compose network and on this machine.

Nothing here is installed on the host. The CA is generated once and kept, so trusting it once
lasts; the issuer's certificate is reissued from it whenever it nears expiry. Written with
`cryptography`, which the image already carries for token validation, so this adds no
dependency.

Layout under the output directory, one directory per consumer so each mounts only what it needs:

    ca/ca.pem                   the CA certificate: what every client trusts
    ca-key/ca-key.pem           the CA private key: read only by this script
    keycloak/cert.pem           the issuer's certificate
    keycloak/key.pem            the issuer's private key

Local-only material. A deployment reachable by anything else uses a certificate from its own
ingress, and none of this.
"""

from __future__ import annotations

import datetime
import sys
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

# The names the issuer answers to. `keycloak.localhost` is the one every party uses; `localhost`
# is there so a person probing the port directly is not also debugging a name mismatch.
NAMES = ("keycloak.localhost", "localhost")

CA_LIFETIME = datetime.timedelta(days=3650)
# Under 398 days, the longest a TLS server certificate may be valid and still be accepted by
# macOS and the browsers, private CA or not.
LEAF_LIFETIME = datetime.timedelta(days=397)
REISSUE_WITHIN = datetime.timedelta(days=30)


def _write(path: Path, data: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    path.chmod(mode)


def _key_pem(key: ec.EllipticCurvePrivateKey) -> bytes:
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


def _authority(
    root: Path, now: datetime.datetime
) -> tuple[x509.Certificate, ec.EllipticCurvePrivateKey]:
    cert_path, key_path = root / "ca" / "ca.pem", root / "ca-key" / "ca-key.pem"
    if cert_path.exists() and key_path.exists():
        cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
        key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
        if not isinstance(key, ec.EllipticCurvePrivateKey):
            raise SystemExit(f"tls: {key_path} is not the EC key this script writes")
        return cert, key

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "CFOKit local development CA")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + CA_LIFETIME)
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=False,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False
        )
        .sign(key, hashes.SHA256())
    )
    # The CA key signs whatever it is asked to; readable by its owner alone.
    _write(key_path, _key_pem(key), 0o600)
    _write(cert_path, cert.public_bytes(serialization.Encoding.PEM), 0o644)
    return cert, key


def _needs_leaf(path: Path, ca: x509.Certificate, now: datetime.datetime) -> bool:
    if not path.exists():
        return True
    leaf = x509.load_pem_x509_certificate(path.read_bytes())
    return leaf.issuer != ca.subject or leaf.not_valid_after_utc - now < REISSUE_WITHIN


def main(root: Path) -> int:
    now = datetime.datetime.now(datetime.UTC)
    ca, ca_key = _authority(root, now)
    cert_path = root / "keycloak" / "cert.pem"
    if not _needs_leaf(cert_path, ca, now):
        print("tls: certificates current")
        return 0

    key = ec.generate_private_key(ec.SECP256R1())
    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, NAMES[0])]))
        .issuer_name(ca.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + LEAF_LIFETIME)
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName(n) for n in NAMES]), critical=False
        )
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )
    # Readable by the issuer's own user, which is not this one. Local-only material; see above.
    _write(root / "keycloak" / "key.pem", _key_pem(key), 0o644)
    _write(cert_path, cert.public_bytes(serialization.Encoding.PEM), 0o644)
    print(f"tls: issued a certificate for {', '.join(NAMES)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
