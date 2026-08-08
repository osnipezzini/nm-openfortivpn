# Build environment for the plasma-nm openfortivpn plugin.
# Base image MUST match your host distro so the produced .so links against
# the same Qt6/KF6 versions your Plasma session uses.
ARG BASE_IMAGE=ubuntu:26.04
FROM ${BASE_IMAGE}

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
        ninja-build \
        git \
        pkg-config \
        extra-cmake-modules \
        qt6-base-dev \
        qt6-declarative-dev \
        qtkeychain-qt6-dev \
        qcoro-qt6-dev \
        libnm-dev \
        libssl-dev \
        libkf6coreaddons-dev \
        libkf6dbusaddons-dev \
        libkf6i18n-dev \
        libkf6completion-dev \
        libkf6config-dev \
        libkf6kio-dev \
        libkf6jobwidgets-dev \
        libkf6notifications-dev \
        libkf6service-dev \
        libkf6solid-dev \
        libkf6widgetsaddons-dev \
        libkf6windowsystem-dev \
        libkf6colorscheme-dev \
        libkf6networkmanagerqt-dev \
        libkf6modemmanagerqt-dev \
        libplasma-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY docker/entrypoint.sh /usr/local/bin/plasma-nm-build
RUN chmod +x /usr/local/bin/plasma-nm-build

WORKDIR /src
ENTRYPOINT ["/usr/local/bin/plasma-nm-build"]