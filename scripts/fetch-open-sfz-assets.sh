#!/usr/bin/env bash
set -euo pipefail

asset_root=${1:?usage: fetch-open-sfz-assets.sh ASSET_ROOT}
download_root=$(mktemp -d /tmp/ostinato-open-sfz.XXXXXX)
trap 'rm -rf -- "$download_root"' EXIT

mkdir -p "$asset_root"

download_checked() {
    local url=$1
    local checksum=$2
    local filename=$3

    curl --fail --location --retry 3 --silent --show-error \
        --output "$download_root/$filename" "$url"
    printf '%s  %s\n' "$checksum" "$download_root/$filename" \
        | sha256sum --check --strict
}

download_checked \
    'https://freepats.zenvoid.org/Piano/SalamanderGrandPiano/SalamanderGrandPianoV3%2B20161209_44khz16bit.tar.xz' \
    '58750eb1366761e187f71ddb9b932355ea894d28ec4331e74ab8acb44c819936' \
    'SalamanderGrandPianoV3_44khz16bit.tar.xz'
download_checked \
    'https://github.com/sfzinstruments/karoryfer.meatbass/releases/download/v1.001/Karoryfer.Meatbass.v1.001.zip' \
    'bc053061d4f39fb76ba56bc1f323efa228d1f63757c331738812479bcf04fe96' \
    'Karoryfer.Meatbass.v1.001.zip'
download_checked \
    'https://github.com/sfzinstruments/karoryfer.swirly-drums/releases/download/v1.104/Swirly.Drums_1104.zip' \
    'dbeb1ad04052da1bada490ced8cc7d9fdd3b21ea90f7c6020269968b70f836c3' \
    'Swirly.Drums_1104.zip'
download_checked \
    'https://github.com/sfzinstruments/karoryfer.shinyguitar/releases/download/v1.002/Karoryfer.Shinyguitar.v1.002.zip' \
    '23cf4030cbf9ce9e2c84d7cbb1c022fbca124bfff0ad118a14eda7cf6c921d7b' \
    'Karoryfer.Shinyguitar.v1.002.zip'
download_checked \
    'https://github.com/sfzinstruments/karoryfer.black-and-blue-basses/releases/download/v1.002/Black_And_Blue_Basses_1002.zip' \
    'cf77fc782abf996826fe75cfd948d356968de7c8b967c471c6a433835d2b4f55' \
    'Black_And_Blue_Basses_1002.zip'

tar --extract --xz \
    --file "$download_root/SalamanderGrandPianoV3_44khz16bit.tar.xz" \
    --directory "$asset_root"
unzip -q "$download_root/Karoryfer.Meatbass.v1.001.zip" \
    -d "$asset_root"
mkdir -p "$asset_root/Swirly Drums"
unzip -q "$download_root/Swirly.Drums_1104.zip" \
    -d "$asset_root/Swirly Drums"
unzip -q "$download_root/Karoryfer.Shinyguitar.v1.002.zip" \
    -d "$asset_root"
mkdir -p "$asset_root/Black Blue Basses"
unzip -q "$download_root/Black_And_Blue_Basses_1002.zip" \
    -d "$asset_root/Black Blue Basses"

vsco_repository="$download_root/vsco2"
vsco_commit='6dd651d55dde97fd4028699be9d4481f26917891'
git init --quiet "$vsco_repository"
git -C "$vsco_repository" remote add origin \
    https://github.com/sgossner/VSCO-2-CE.git
git -C "$vsco_repository" -c protocol.version=2 fetch --quiet \
    --depth 1 --filter=blob:none origin "$vsco_commit"
mkdir -p "$asset_root/VSCO2"
git -C "$vsco_repository" archive FETCH_HEAD \
    LICENSE \
    FluteSusVib.sfz \
    ClarinetStac.sfz \
    TrumpetStac.sfz \
    SViolinVib-Quiet.sfz \
    CelloEnsSusVib-Quiet.sfz \
    'Woodwinds/Flute/susvib' \
    'Woodwinds/Clarinet/stac' \
    'Brass/Trumpet/stac' \
    'Strings/Solo Violin/Arco Vib' \
    'Strings/Cello Section/susvib' \
    | tar --extract --directory "$asset_root/VSCO2"

virtuosity_repository="$download_root/virtuosity-drums"
virtuosity_commit='9f04cf9a734527edfbb0a4eee1f674e45bbf71bc'
git init --quiet "$virtuosity_repository"
git -C "$virtuosity_repository" remote add origin \
    https://github.com/sfzinstruments/virtuosity_drums.git
git -C "$virtuosity_repository" -c protocol.version=2 fetch --quiet \
    --depth 1 --filter=blob:none origin "$virtuosity_commit"
mkdir -p "$asset_root/Virtuosity Drums"
git -C "$virtuosity_repository" archive FETCH_HEAD \
    | tar --extract --directory "$asset_root/Virtuosity Drums"

test -f "$asset_root/SalamanderGrandPianoV3_44.1khz16bit/SalamanderGrandPianoV3.sfz"
test -f "$asset_root/Meatbass/Programs/04_pizz.sfz"
test -f "$asset_root/Swirly Drums/Programs/Basic_kit.sfz"
test -f "$asset_root/VSCO2/FluteSusVib.sfz"
test -f "$asset_root/VSCO2/ClarinetStac.sfz"
test -f "$asset_root/VSCO2/TrumpetStac.sfz"
test -f "$asset_root/VSCO2/SViolinVib-Quiet.sfz"
test -f "$asset_root/VSCO2/CelloEnsSusVib-Quiet.sfz"
test -f "$asset_root/Shinyguitar/Programs/acoustic.sfz"
test -f "$asset_root/Shinyguitar/Programs/main.sfz"
test -f "$asset_root/Black Blue Basses/Programs/05-darkblack_pluck.sfz"
test -f "$asset_root/Black Blue Basses/Programs/03-babyblue_all.sfz"
test -f "$asset_root/Virtuosity Drums/Programs/02-full-kit.sfz"
