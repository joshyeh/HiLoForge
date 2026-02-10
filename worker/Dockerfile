FROM python:3.11-slim

ARG BLENDER_VERSION=4.2.5
ENV BLENDER_VERSION=${BLENDER_VERSION}

# Tools needed to download/unpack blender
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl xz-utils zip \
    libx11-6 libxi6 libxrender1 libxrandr2 libxfixes3 libxkbcommon0 \
    libxcursor1 libxinerama1 libxxf86vm1 libegl1 libgl1 \
    libglib2.0-0 libsm6 libice6 \
  && rm -rf /var/lib/apt/lists/*

# Download Blender official tarball
RUN mkdir -p /opt/blender \
 && curl -L -o /tmp/blender.tar.xz "https://download.blender.org/release/Blender4.2/blender-${BLENDER_VERSION}-linux-x64.tar.xz" \
 && tar -xf /tmp/blender.tar.xz -C /opt/blender --strip-components=1 \
 && rm /tmp/blender.tar.xz

ENV PATH="/opt/blender:${PATH}"

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY worker.py .
COPY blender_process.py .

CMD ["python", "worker.py"]
