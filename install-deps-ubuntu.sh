#!/usr/bin/env bash
set -euo pipefail

usage() {
	printf 'Usage: %s [--no-openocd]
' "${0##*/}"
	printf '
'
	printf 'Install Ubuntu/Debian host dependencies for building NGCCM4.
'
	printf '
'
	printf 'Options:
'
	printf '  --no-openocd  Skip OpenOCD when hardware flashing is not needed.
'
	printf '  -h, --help    Show this help text.
'
}

install_openocd=1

while [ "$#" -gt 0 ]; do
	case "$1" in
		--no-openocd)
			install_openocd=0
			;;
		-h|--help)
			usage
			exit 0
			;;
		*)
			printf 'error: unknown option: %s
' "$1" >&2
			usage >&2
			exit 2
			;;
	esac
	shift
done

if ! command -v apt-get >/dev/null 2>&1; then
	printf 'error: this installer expects apt-get on Ubuntu/Debian.
' >&2
	exit 1
fi

packages=(
	build-essential
	gcc-arm-none-eabi
	binutils-arm-none-eabi
	libnewlib-arm-none-eabi
	python3
	qemu-system-arm
)

if [ "$install_openocd" -eq 1 ]; then
	packages+=(openocd)
fi

sudo apt-get update
sudo apt-get install -y "${packages[@]}"

printf '
Installed NGCCM4 host dependencies.
'
printf 'Quick verification:
'
arm-none-eabi-gcc --version | head -n 1
python3 --version
qemu-system-arm --version | head -n 1
if [ "$install_openocd" -eq 1 ]; then
	openocd --version | head -n 1
fi
