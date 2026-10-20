"""Resolve the four current public AAC components once for a demo run.

Only ./demo prepare writes the run selection. Ordinary up/run/maintenance reads
it unchanged. No private repository, credentials or mutable Docker latest tag.
"""
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.request import urlopen

SITE = "https://docs.cascadeauth.com/released-components.json"
PACKAGES = ("aac-cli", "aac-invoke-auth", "aac-trust-anchor-publisher")


def read_json(url):
    with urlopen(url, timeout=30) as response:
        return json.load(response)


def image_digest(reference):
    # Buildx before 0.33 (Ubuntu 24.04 packages 0.30) prints its default summary
    # for any --format that starts with "{{.Manifest"; this spelling avoids that.
    digest = subprocess.check_output(
        ["docker", "buildx", "imagetools", "inspect", reference, "--format", '{{printf "%s" .Manifest.Digest}}'],
        text=True).strip()
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise ValueError("registry returned no image digest")
    return reference.split("@", 1)[0] + "@" + digest


def resolve_packages():
    """Select Python companions without discovering any container or sidecar."""
    packages = {}
    for name in PACKAGES:
        metadata = read_json(f"https://pypi.org/pypi/{name}/json")
        version = metadata["info"]["version"]
        if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
            raise ValueError("current package is not a stable release: " + name)
        wheels = [f for f in metadata["urls"] if f["packagetype"] == "bdist_wheel" and not f["yanked"]]
        if len(wheels) != 1:
            raise ValueError("expected the single public pure-Python wheel: " + name)
        wheel = wheels[0]
        packages[name] = {"version": version, "url": wheel["url"], "sha256": wheel["digests"]["sha256"]}
    return {"schema_version": 1, "packages": packages}


def load_selection(path):
    """Read explicit package pins; never repair them through live discovery."""
    record = json.loads(path.read_text())
    if record.get("schema_version") != 1 or set(record.get("packages", {})) != set(PACKAGES):
        raise ValueError("selection requires schema_version 1 and all three AAC packages")
    for name, package in record["packages"].items():
        if (not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", package.get("version", ""))
                or not re.fullmatch(r"[0-9a-f]{64}", package.get("sha256", ""))
                or not package.get("url", "").startswith("https://")):
            raise ValueError("selection requires a stable version, HTTPS wheel URL and SHA256: " + name)
    return record


def resolve():
    site = read_json(SITE)
    packages = resolve_packages()["packages"]
    sidecar = site["sidecar"]
    sidecar_image = image_digest("docker.io/cascadeauth/aac-sidecar:" + sidecar["version"])
    if sidecar_image.rsplit("@", 1)[1] != sidecar["image_digest"]:
        raise ValueError("sidecar registry digest differs from the published release record")
    publisher = image_digest("ghcr.io/cascadeauth/aac-trust-anchor-publisher:" + packages["aac-trust-anchor-publisher"]["version"])
    return {"schema_version": 1, "metadata_url": SITE, "packages": packages,
            "sidecar": {"version": sidecar["version"], "image": sidecar_image},
            "publisher": {"image": publisher}}


def selected(root):
    return json.loads((root / ".local/components.json").read_text())


def compose_values(record):
    return {"AAC_DEMO_SIDECAR_IMAGE": record["sidecar"]["image"],
            "AAC_DEMO_PUBLISHER_IMAGE": record["publisher"]["image"],
            "AAC_DEMO_INVOKE_AUTH_VERSION": record["packages"]["aac-invoke-auth"]["version"]}


def package_spec(name, metadata):
    extra = "[fastapi]" if name == "aac-invoke-auth" else ""
    return f"{name}{extra} @ {metadata['url']}#sha256={metadata['sha256']}"


def prepare(root, *, tests=False):
    if sys.prefix == sys.base_prefix:
        raise ValueError("activate your demo virtual environment first")
    path = root / ".local/components.json"
    if path.exists():
        record = selected(root)
    else:
        record = resolve()
        if tuple(map(int, record["packages"]["aac-cli"]["version"].split("."))) < (0, 2, 13):
            raise ValueError("this demo requires public aac-cli 0.2.13 or later; wait for that release")
        record["demo_revision"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x") as stream:
            json.dump(record, stream, indent=2); stream.write("\n")
    names = PACKAGES if tests else ("aac-cli",)
    specs = [package_spec(name, record["packages"][name]) for name in names]
    if tests:
        specs += ["-r", str(root / "tests/requirements.txt")]
    subprocess.run([sys.executable, "-m", "pip", "install", *specs], check=True)
    print("Run selection: " + str(path))
    print(json.dumps({"packages": {k: v["version"] for k, v in record["packages"].items()},
                      "sidecar": record["sidecar"], "publisher": record["publisher"]}, indent=2))


if __name__ == "__main__":
    if sys.argv[1:] != ["--invoke-version"]:
        raise SystemExit("Use ./demo prepare; --invoke-version is the frozen build-version lookup after ./demo prepare")
    print(selected(Path(__file__).resolve().parent)["packages"]["aac-invoke-auth"]["version"])
