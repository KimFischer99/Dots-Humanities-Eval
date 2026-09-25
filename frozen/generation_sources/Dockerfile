ARG BASE_IMAGE=python:3.12-slim-bookworm
FROM ${BASE_IMAGE}
ARG PI_URL
ARG PI_SHA256
# Official self-contained Linux x64 release; no floating npm installation.
RUN PI_URL="$PI_URL" PI_SHA256="$PI_SHA256" python -c "import os,urllib.request,hashlib,tarfile,pathlib,shutil; p=pathlib.Path('/tmp/pi.tgz'); p.write_bytes(urllib.request.urlopen(os.environ['PI_URL'],timeout=120).read()); assert hashlib.sha256(p.read_bytes()).hexdigest()==os.environ['PI_SHA256']; dest=pathlib.Path('/opt/pi-dist'); dest.mkdir(); tarfile.open(p).extractall(dest,filter='data'); hits=[x for x in dest.rglob('pi') if x.is_file()]; assert len(hits)==1; d=pathlib.Path('/opt/pi'); shutil.copytree(hits[0].parent,d); (d/'pi').chmod(0o755); p.unlink()"
RUN mkdir -p /app /workspace && /opt/pi/pi --version
COPY eval.py runtime.py /app/
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PI_OFFLINE=1 PI_SKIP_VERSION_CHECK=1 PI_TELEMETRY=0
USER 10001:10001
WORKDIR /workspace