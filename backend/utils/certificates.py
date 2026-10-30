"""
SSL certificate generation utilities.
"""
import logging
import trustme
from pathlib import Path

log = logging.getLogger(__name__)


def setup_development_certificates():
    """
    Sets up development SSL certificates for local use.

    This function generates a certificate authority (CA) using `trustme`, issues a
    server certificate for `localhost`, and saves the certificates and associated
    keys to a directory named `devcerts`. If the directory already exists, it will
    not be recreated.

    :return: A tuple containing the file paths of the generated server certificate
        (as `.pem` file) and private server key (as `.key` file).
    :rtype: tuple[str, str]
    """
    log.debug("Generating development SSL certificates...")
    ca = trustme.CA()
    server_cert = ca.issue_cert("localhost")
    cert_dir = Path("devcerts")
    cert_dir.mkdir(exist_ok=True)

    server_cert.private_key_and_cert_chain_pem.write_to_path(cert_dir / "server.pem")
    server_cert.private_key_pem.write_to_path(cert_dir / "server.key")
    ca.cert_pem.write_to_path(cert_dir / "ca.pem")

    log.info(f"Development SSL certificates created in {cert_dir}")
    return str(cert_dir / "server.pem"), str(cert_dir / "server.key")
