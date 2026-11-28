"""The real-boot lane for the glass login screen (qa/vm/login_boot.py and its workflow): the parts
that need no virtual machine. The lane itself only runs on GitHub (it needs KVM), so what can
go wrong in it without a VM is caught here: the messages to QEMU, the pictures, the keys
typed on the login screen, the image and checksum names, and which steps run."""
from __future__ import annotations

import base64
import importlib.util
import json
import re
import struct
import subprocess
import sys
import zlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
VM = ROOT / "qa/vm"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


lb = _load("lgv_login_boot", VM / "login_boot.py")
probe = _load("lgv_probe", VM / "guest/probe.py")


# ---- QMP ---------------------------------------------------------------------------------------

def test_qmp_messages_are_one_json_line_each():
    assert lb.qmp_message("qmp_capabilities") == b'{"execute": "qmp_capabilities"}\r\n'
    msg = json.loads(lb.qmp_message("screendump", filename="/tmp/a.ppm"))
    assert msg == {"execute": "screendump", "arguments": {"filename": "/tmp/a.ppm"}}


def test_send_key_uses_qcodes_and_a_hold_time():
    msg = json.loads(lb.send_key_message(["ret"], hold_ms=80))
    assert msg == {"execute": "send-key", "arguments": {"keys": [{"type": "qcode", "data": "ret"}], "hold-time": 80}}


def test_the_password_is_typed_with_plain_keys_only():
    assert lb.keys_for_text(lb.PASSWORD) == ["g", "l", "a", "s", "s", "t", "e", "s", "t", "1"]
    assert lb.keys_for_text("a b-c.\n") == ["a", "spc", "b", "minus", "c", "dot", "ret"]
    for bad in ("A", "!", "é", "_"):                    # Shift or a layout would change these
        with pytest.raises(ValueError):
            lb.keys_for_text(bad)
    assert re.fullmatch(r"[a-z0-9]+", lb.PASSWORD)


def test_qmp_client_skips_events_and_raises_on_errors():
    import socket
    import threading
    ours, theirs = socket.socketpair()
    ours.settimeout(5)
    seen = []

    def serve():
        c = theirs
        f = c.makefile("rwb")
        f.write(b'{"QMP": {"version": {}, "capabilities": []}}\r\n'); f.flush()
        for reply in (b'{"return": {}}\r\n',
                      b'{"event": "RESET", "data": {}}\r\n{"return": {"qemu": {"major": 9}}}\r\n',
                      b'{"error": {"class": "GenericError", "desc": "nope"}}\r\n'):
            seen.append(json.loads(f.readline()))
            f.write(reply); f.flush()
        c.close()
    t = threading.Thread(target=serve, daemon=True)
    t.start()
    q = lb.Qmp(ours)
    assert q.execute("query-version") == {"qemu": {"major": 9}}
    with pytest.raises(RuntimeError, match="nope"):
        q.send_keys(["esc"])
    q.close()
    t.join(5)
    assert [m["execute"] for m in seen] == ["qmp_capabilities", "query-version", "send-key"]


# ---- pictures ----------------------------------------------------------------------------------

def _ppm(w, h, pixel=lambda x, y: (x * 10 % 256, y * 20 % 256, 128), comment=True):
    rgb = bytes(c for y in range(h) for x in range(w) for c in pixel(x, y))
    head = b"P6\n# made by a test\n" if comment else b"P6\n"
    return head + f"{w} {h}\n255\n".encode() + rgb, rgb


def _decode_png(data: bytes):
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    pos, chunks = 8, []
    while pos < len(data):
        n, = struct.unpack(">I", data[pos:pos + 4])
        kind, body = data[pos + 4:pos + 8], data[pos + 8:pos + 8 + n]
        crc, = struct.unpack(">I", data[pos + 8 + n:pos + 12 + n])
        assert zlib.crc32(kind + body) & 0xFFFFFFFF == crc, kind
        chunks.append((kind, body))
        pos += 12 + n
    assert [k for k, _ in chunks] == [b"IHDR", b"IDAT", b"IEND"]
    w, h, depth, colour, *_ = struct.unpack(">IIBBBBB", chunks[0][1])
    assert (depth, colour) == (8, 2)
    raw = zlib.decompress(chunks[1][1])
    rows = [raw[y * (w * 3 + 1):(y + 1) * (w * 3 + 1)] for y in range(h)]
    assert all(r[0] == 0 for r in rows)
    return w, h, b"".join(r[1:] for r in rows)


def test_ppm_from_qemu_becomes_a_valid_png():
    data, rgb = _ppm(7, 5)
    pic = lb.read_ppm(data)
    assert (pic.width, pic.height, pic.rgb) == (7, 5, rgb)
    assert _decode_png(lb.png_bytes(pic)) == (7, 5, rgb)
    assert lb.read_ppm(_ppm(3, 2, comment=False)[0]).width == 3
    with pytest.raises(ValueError):
        lb.read_ppm(b"P5\n3 2\n255\n" + bytes(6))


def test_shrink_mean_colour_and_difference():
    grey = lb.Picture(640, 400, bytes([40, 40, 40]) * 640 * 400)
    small = lb.shrink(grey, 240)
    assert (small.width, small.height) == (240, 150)
    assert lb.mean_colour(small) == (40, 40, 40)
    half = lb.Picture(4, 2, bytes([0, 0, 0, 0, 0, 0, 200, 100, 50, 200, 100, 50] * 2))
    assert lb.shrink(half, 2).rgb == bytes([0, 0, 0, 200, 100, 50] * 1)
    assert lb.shrink(half, 1).rgb == bytes([100, 50, 25])
    assert lb.shrink(grey, 5000).width == 640               # never wider than the picture
    bright = lb.Picture(640, 400, bytes([230, 120, 60]) * 640 * 400)
    assert lb.difference(grey, grey) == 0
    assert lb.difference(grey, bright) == pytest.approx((190 + 80 + 20) / 3)
    assert lb.difference(grey, bright) >= lb.CLEARLY_DIFFERENT > lb.ABOUT_THE_SAME
    # A clock-sized change on the plain screen stays well under "about the same".
    rgb = bytearray(grey.rgb)
    for y in range(20, 60):
        for x in range(300, 340):
            rgb[(y * 640 + x) * 3:(y * 640 + x) * 3 + 3] = b"\xff\xff\xff"
    assert lb.difference(grey, lb.Picture(640, 400, bytes(rgb))) < lb.ABOUT_THE_SAME
    other_shape = lb.Picture(320, 100, bytes([40, 40, 40]) * 320 * 100)
    assert lb.difference(grey, other_shape) == 0


def test_thumbnail_in_the_log_decodes_to_a_240_px_png():
    pic = lb.Picture(1280, 800, bytes([10, 20, 30]) * 1280 * 800)
    block = lb.thumbnail_block(pic, "01-plain").splitlines()
    assert block[0] == "----- BEGIN PNG 01-plain (240x150) -----"
    assert block[-1] == "----- END PNG 01-plain -----"
    assert all(len(l) <= 76 for l in block[1:-1])
    w, h, rgb = _decode_png(base64.b64decode("".join(block[1:-1])))
    assert (w, h) == (240, 150) and rgb[:3] == bytes([10, 20, 30])


def test_the_test_picture_is_a_small_jpeg():
    data = (VM / "test-picture.jpg").read_bytes()
    assert data[:3] == b"\xff\xd8\xff" and len(data) < 64 * 1024


# ---- images, checksums and signatures -------------------------------------------------------

FEDORA_INDEX = """<html><body><pre>
<a href="../">../</a>
<a href="Fedora-Cloud-44-1.6-x86_64-CHECKSUM">Fedora-Cloud-44-1.6-x86_64-CHECKSUM</a>
<a href="Fedora-Cloud-44-1.7-x86_64-CHECKSUM">Fedora-Cloud-44-1.7-x86_64-CHECKSUM</a>
<a href="Fedora-Cloud-Base-AmazonEC2-44-1.7.x86_64.raw.xz">Fedora-Cloud-Base-AmazonEC2-44-1.7.x86_64.raw.xz</a>
<a href="Fedora-Cloud-Base-Generic-44-1.6.x86_64.qcow2">x</a>
<a href="Fedora-Cloud-Base-Generic-44-1.7.x86_64.qcow2">x</a>
<a href="Fedora-Cloud-Base-Generic-44-1.10.x86_64.qcow2?C=M">sort link</a>
</pre></body></html>"""


def test_fedora_image_and_its_checksum_file_are_found_on_the_index_page():
    names = lb.links(FEDORA_INDEX)
    assert "../" not in names and "" not in names
    assert lb.pick_fedora(names, "44") == ("Fedora-Cloud-Base-Generic-44-1.7.x86_64.qcow2",
                                           "Fedora-Cloud-44-1.7-x86_64-CHECKSUM")
    # 1.10 is newer than 1.7 (numbers, not text), but needs its own CHECKSUM file.
    with pytest.raises(LookupError, match="1.10"):
        lb.pick_fedora(names + ["Fedora-Cloud-Base-Generic-44-1.10.x86_64.qcow2"], "44")
    with pytest.raises(LookupError):
        lb.pick_fedora(names, "45")
    dev = ["Fedora-Cloud-Base-Generic-45-20261101.n.0.x86_64.qcow2", "Fedora-Cloud-45-20261101.n.0-x86_64-CHECKSUM"]
    assert lb.pick_fedora(dev, "45")[0] == dev[0]
    assert lb.fedora_index_urls("45")[0] == "https://dl.fedoraproject.org/pub/fedora/linux/releases/45/Cloud/x86_64/images/"


def test_arch_prefers_the_dated_image():
    names = lb.links('<a href="Arch-Linux-x86_64-cloudimg.qcow2">a</a><a href="Arch-Linux-x86_64-cloudimg-20261101.471820.qcow2">b</a>'
                     '<a href="Arch-Linux-x86_64-cloudimg-20261015.466000.qcow2">c</a><a href="Arch-Linux-x86_64-cloudimg-20261101.471820.qcow2.sig">d</a>')
    assert lb.pick_arch(names) == "Arch-Linux-x86_64-cloudimg-20261101.471820.qcow2"
    assert lb.pick_arch(["Arch-Linux-x86_64-cloudimg.qcow2"]) == "Arch-Linux-x86_64-cloudimg.qcow2"
    with pytest.raises(LookupError):
        lb.pick_arch(["Arch-Linux-x86_64-basic.qcow2"])


def test_ubuntu_urls_use_the_codename_folder():
    d = lb.DISTROS["ubuntu-26.10"]
    assert lb.ubuntu_base_url(d["codename"]) == "https://cloud-images.ubuntu.com/releases/stonking/release/"
    assert lb.DISTROS["ubuntu-26.04"]["codename"] == "resolute"


def test_checksum_lists_in_both_forms():
    fedora = ("# Fedora-Cloud-Base-Generic-44-1.7.x86_64.qcow2: 562298880 bytes\n"
              f"SHA256 (Fedora-Cloud-Base-Generic-44-1.7.x86_64.qcow2) = {'AB' * 32}\n"
              f"SHA512 (other) = {'c' * 128}\n")
    assert lb.parse_checksums(fedora) == {"Fedora-Cloud-Base-Generic-44-1.7.x86_64.qcow2": "ab" * 32}
    ubuntu = f"{'1' * 64} *ubuntu-26.04-server-cloudimg-amd64.img\n{'2' * 64}  plain-name.tar.gz\nnot a line\n"
    assert lb.parse_checksums(ubuntu) == {"ubuntu-26.04-server-cloudimg-amd64.img": "1" * 64, "plain-name.tar.gz": "2" * 64}


def test_gpg_status_needs_a_good_and_valid_signature():
    ok = ("[GNUPG:] NEWSIG\n[GNUPG:] GOODSIG 1A5D6C4C7DB87C81 UEC Image Automatic Signing Key <cdimage@ubuntu.com>\n"
          "[GNUPG:] VALIDSIG AAAA 2026-10-20 1792514694 0 4 0 1 10 00 D2EB44626FDDC30B513D5BB71A5D6C4C7DB87C81\n")
    assert lb.parse_gpg_status(ok) == {"good": True, "fpr": "AAAA", "primary": lb.UBUNTU_KEY}
    assert not lb.parse_gpg_status(ok + "[GNUPG:] BADSIG 1A5D x\n")["good"]
    assert not lb.parse_gpg_status("[GNUPG:] GOODSIG 1A5D x\n")["good"]          # no VALIDSIG
    assert not lb.parse_gpg_status("[GNUPG:] ERRSIG 1A5D 1 10 00 0 9\n[GNUPG:] NO_PUBKEY 1A5D\n")["good"]


def test_shipped_arch_boxes_key_dearmors_and_names_the_pinned_fingerprint():
    asc = (VM / "keys/arch-boxes.asc").read_bytes()
    binary = lb.dearmor(asc)
    assert binary[0] & 0x80 and len(binary) > 200                  # an OpenPGP packet
    assert lb.dearmor(binary) == binary                            # binary stays as it is
    assert lb.dearmor(asc + b"\n" + asc) == binary * 2             # several blocks
    # The fingerprint of a v4 key is the SHA-1 of 0x99, the key packet's length and its body.
    tag, length = binary[0], binary[1]
    assert tag == 0x98                                             # old format, public key, 1 byte length
    import hashlib
    fpr = hashlib.sha1(b"\x99" + struct.pack(">H", length) + binary[2:2 + length]).hexdigest().upper()
    assert fpr == lb.ARCH_BOXES_KEY


def test_key_uids_from_gpg_colons():
    colons = ("pub:-:255:22:E0B78BF4326C6F8F:1653836204:::-:::cSC:::::ed25519:::0:\n"
              "fpr:::::::::1B9A16984A4E8CB448712D2AE0B78BF4326C6F8F:\n"
              "uid:-::::1653836204::514C::arch-boxes <arch-boxes@archlinux.org>::::::::::0:\n"
              "sub:-:255:22:343635A6859A9174:1653836263:1811516263:::::s::::ed25519::\n"
              "fpr:::::::::656E4C5AC1CC3B86E539D97E343635A6859A9174:\n"
              "pub:-:4096:1:AAAA:1:::-:::scSC::::::23::0:\nfpr:::::::::BBBB:\n"
              "uid:-::::1::X::Fedora (45) <fedora-45-primary@fedoraproject.org>::::::::::0:\n")
    assert lb.key_uids(colons) == {"1B9A16984A4E8CB448712D2AE0B78BF4326C6F8F": ["arch-boxes <arch-boxes@archlinux.org>"],
                                   "BBBB": ["Fedora (45) <fedora-45-primary@fedoraproject.org>"]}


# ---- the steps ---------------------------------------------------------------------------------

def test_the_twelve_steps_in_order_with_removal_last():
    assert lb.plan() == ["baseline", "on", "glass", "login", "update", "restart", "addon-update", "off", "crash",
                         "broken-addon", "no-login", "removal"]
    for name, needs in lb.STEPS:
        for n in needs:
            assert lb.ORDER.index(n) < lb.ORDER.index(name), (name, n)
        assert hasattr(lb.Lane, "step_" + name.replace("-", "_")), name


def test_plan_adds_what_a_step_builds_on():
    assert lb.plan(["update"]) == ["baseline", "on", "glass", "login", "update"]
    assert lb.plan(["restart"]) == ["baseline", "on", "glass", "login", "update", "restart"]
    assert lb.plan(["removal", "crash"]) == ["baseline", "crash", "removal"]
    assert lb.plan(["addon-update"]) == ["baseline", "on", "glass", "login", "update", "restart", "addon-update"]
    assert lb.plan(["off"]) == ["baseline", "on", "off"]
    with pytest.raises(ValueError, match="nope"):
        lb.plan(["crash", "nope"])


def test_a_step_is_skipped_only_when_its_groundwork_failed():
    results = {"baseline": "PASS", "on": "PASS", "glass": "FAIL"}
    assert lb.blocked_by("login", results) == "glass"
    assert lb.blocked_by("update", {**results, "login": "SKIP"}) == "login"
    assert lb.blocked_by("restart", {**results, "login": "PASS", "update": "FAIL"}) == "update"
    assert lb.blocked_by("off", results) == ""                     # off needs only on
    for breaker in ("crash", "broken-addon", "no-login", "removal"):
        assert lb.blocked_by(breaker, results) == ""               # each starts clean
        assert lb.blocked_by(breaker, {"baseline": "FAIL"}) == "baseline"


def test_dconf_listing_differences():
    base = [{"path": ".", "kind": "d", "mode": "0o755", "owner": "0:0"},
            {"path": "db/gdm", "kind": "f", "mode": "0o644", "owner": "0:0", "sha256": "a", "compiled": True},
            {"path": "db/gdm.d/00-upstream", "kind": "f", "mode": "0o644", "owner": "0:0", "sha256": "b", "compiled": False}]
    same_settings_new_bytes = [dict(base[0]), {**base[1], "sha256": "z"}, dict(base[2])]
    assert lb.listing_differences(base, same_settings_new_bytes) == []
    left = base + [{"path": "db/gdm.d/50-fedora-glass", "kind": "f", "mode": "0o644", "owner": "0:0", "sha256": "c", "compiled": False}]
    assert lb.listing_differences(base, left) == ["new: db/gdm.d/50-fedora-glass"]
    edited = [base[0], base[1], {**base[2], "sha256": "x"}]
    assert lb.listing_differences(base, edited) == ["changed sha256: db/gdm.d/00-upstream (b -> x)"]
    assert lb.listing_differences(base, base[:2]) == ["gone: db/gdm.d/00-upstream"]


def test_sessions_are_told_apart_by_class():
    state = {"sessions": [
        {"id": "c1", "user": "gdm-greeter", "class": "greeter", "type": "wayland", "gnome_shell": True},
        {"id": "3", "user": "tester", "class": "manager", "type": "unspecified", "gnome_shell": False},
        {"id": "4", "user": "tester", "class": "user", "type": "wayland", "gnome_shell": True}]}
    assert [s["id"] for s in lb.greeters(state)] == ["c1"]
    assert [s["id"] for s in lb.user_sessions(state)] == ["4"]


def test_cloud_init_seed_makes_the_one_test_user():
    ud, md = lb.cloud_init_seed("ssh-ed25519 AAAAC3Nza login-boot\n", "lgv-arch-1")
    assert ud.startswith("#cloud-config\n")
    assert f"- name: {lb.USER}" in ud and f"plain_text_passwd: {lb.PASSWORD}" in ud
    assert 'sudo: "ALL=(ALL) NOPASSWD:ALL"' in ud and "lock_passwd: false" in ud
    assert "      - ssh-ed25519 AAAAC3Nza login-boot\n" in ud and "ssh_pwauth: false" in ud
    assert md == "instance-id: lgv-arch-1\nlocal-hostname: glass-test\n"
    yaml = pytest.importorskip("yaml")
    doc = yaml.safe_load(ud)
    assert doc["users"][0]["name"] == "tester" and doc["chpasswd"] == {"expire": False}


def test_ssh_is_loopback_only_and_never_stores_the_host_key(tmp_path):
    vm = lb.VM("fedora-45", tmp_path, tmp_path)
    argv = vm.ssh_argv()
    assert argv[-1] == "tester@127.0.0.1" and "2222" in argv
    assert "UserKnownHostsFile=/dev/null" in argv and "StrictHostKeyChecking=no" in argv and "BatchMode=yes" in argv


# ---- the guest probe ---------------------------------------------------------------------------

def test_probe_health_note_has_the_contract_form():
    note = probe.make_note("0123456789abcdef0123456789abcdef", "b00t", "starting")
    assert note == {"v": 1, "token": "0123456789abcdef0123456789abcdef", "boot": "b00t", "phase": "starting", "verified": ""}
    with pytest.raises(ValueError):
        probe.make_note("0123456789abcdef0123456789abcdef", "b", "crashed")
    with pytest.raises(ValueError):
        probe.make_note("not-a-token", "b", "ok")


def test_probe_lists_etc_dconf_with_compiled_databases_marked(tmp_path):
    (tmp_path / "db/gdm.d/locks").mkdir(parents=True)
    (tmp_path / "db/gdm").write_bytes(b"GVariant")
    (tmp_path / "db/gdm.d/00-upstream").write_text("[org/gnome/login-screen]\n")
    (tmp_path / "profile").mkdir()
    (tmp_path / "profile/gdm").write_text("user-db:user\nsystem-db:gdm\n")
    entries = {e["path"]: e for e in probe.etc_listing(str(tmp_path))}
    assert set(entries) == {".", "db", "db/gdm", "db/gdm.d", "db/gdm.d/00-upstream", "db/gdm.d/locks", "profile", "profile/gdm"}
    assert entries["db/gdm"]["compiled"] is True and entries["db/gdm.d/00-upstream"]["compiled"] is False
    assert entries["db/gdm.d"]["kind"] == "d" and len(entries["profile/gdm"]["sha256"]) == 64


def test_probe_finds_denials_of_both_kinds():
    assert probe.DENIAL.search('type=AVC msg=audit(1.2:3): avc:  denied  { read } for comm="gnome-shell"')
    assert probe.DENIAL.search('audit: type=1400 apparmor="DENIED" operation="open" profile="x"')
    assert not probe.DENIAL.search('avc:  granted  { setenforce }')


# ---- syntax of the shell parts and the workflow ----------------------------------------------

def test_guest_setup_script_parses_and_builds_like_the_package_workflow():
    subprocess.run(["bash", "-n", str(VM / "guest/setup.sh")], check=True)
    text = (VM / "guest/setup.sh").read_text()
    assert "rpmbuild -bb --nocheck" in text
    assert "sh packaging/deb/build-deb.sh" in text and "sh packaging/arch/build-pkg.sh" in text
    assert 'dnf -y -q install "$rpm"' in text and "apt_get install -y -qq \"$tree/out/fedora-glass_" in text
    assert "pacman -U --noconfirm" in text
    assert "gnome-initial-setup-done" in text and "set-default graphical.target" in text
    assert "gnome-initial-setup" not in re.sub(r"#.*|gnome-initial-setup-done", "", text)    # never installed


def _workflow():
    from tests.test_workflows import _yaml
    return _yaml("login-boot.yml")


def test_workflow_is_label_gated_read_only_and_lean():
    from tests.test_workflows import _event, _fill, _job_runs
    doc = _workflow()
    assert doc[True]["pull_request"]["types"] == ["labeled", "synchronize"]
    assert "workflow_dispatch" in doc[True]
    assert doc["permissions"] == {"contents": "read"}
    job = doc["jobs"]["boot"]
    assert job["permissions"] == {"contents": "read"} and job["timeout-minutes"] == 45
    assert job["runs-on"] == "ubuntu-latest"
    assert job["strategy"]["fail-fast"] is False
    assert job["strategy"]["matrix"]["distro"] == ["fedora-45", "fedora-44", "ubuntu-26.04", "ubuntu-26.10", "arch"]
    assert set(job["strategy"]["matrix"]["distro"]) == set(lb.DISTROS)
    base = "login-boot-refs/pull/7/merge"

    def run(event, **kw):
        ctx = _event(event, **kw)
        return _job_runs(job, ctx), _fill(doc["concurrency"]["group"], ctx)
    assert run("pull_request", action="synchronize", labels=["login-boot"]) == (True, base)
    assert run("pull_request", action="labeled", label="login-boot", labels=["login-boot"]) == (True, base)
    for other in ("bug", "packages", "release-checks"):
        started, group = run("pull_request", action="labeled", label=other, labels=["login-boot", other])
        assert not started and group != base and group.startswith(base)
    assert run("pull_request", action="synchronize", labels=["packages"])[0] is False
    assert run("workflow_dispatch") == (True, base)


def test_workflow_steps_pin_actions_and_keep_evidence_three_days():
    text = (ROOT / ".github/workflows/login-boot.yml").read_text()
    for uses in re.findall(r"uses:\s*(\S+)", text):
        assert re.fullmatch(r"[\w-]+/[\w-]+@[0-9a-f]{40}", uses), uses
    doc = _workflow()
    steps = doc["jobs"]["boot"]["steps"]
    kvm = next(s for s in steps if "kvm" in s.get("name", "").lower())
    assert "99-kvm4all.rules" in kvm["run"] and "udevadm trigger --name-match=kvm" in kvm["run"]
    drive = next(s for s in steps if "login_boot.py" in s.get("run", ""))
    assert drive["env"]["DISTRO"] == "${{ matrix.distro }}" and "${{" not in drive["run"]
    keep = next(s for s in steps if s.get("uses", "").startswith("actions/upload-artifact@"))
    assert keep["if"] == "always()" and keep["with"]["retention-days"] == 3
    checkout = next(s for s in steps if s.get("uses", "").startswith("actions/checkout@"))
    assert checkout["with"]["persist-credentials"] is False


# ---- the steps against a pretend PC ------------------------------------------------------------
# The lane can only really run on GitHub, so every step's code is run here once against a fake
# guest that behaves as the contract says: a typo in a step that rarely runs shows up here,
# not after half an hour of booting.

class _Clock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, s):
        self.now += s

    def time(self):
        return 1_800_000_000 + self.now


class _FakeQmp:
    def __init__(self, guest):
        self.guest = guest

    def send_keys(self, keys, hold_ms=60):
        self.guest.key(keys)


class _FakeGuest:
    """A PC with GDM and the package, as far as the lane can see it."""

    def __init__(self, guard_works=True, glass_draws=True, guard_too_eager=False, confirm_after=0, path_state="active",
                 addon_confirm_after=0, update_keeps_token=False, watcher="stops", stop_after=2,
                 shell_journal=(), gdm_retries=0, leaves_a_lock=False, guard_condition="yes", prompt_says=None,
                 journal_exit=0, clock=True):
        self.leaves_a_lock, self.guard_condition = leaves_a_lock, guard_condition
        self.shell_journal, self.gdm_pending = list(shell_journal), gdm_retries
        # What the add-on says in GNOME Shell's journal once a user is picked on the glass login
        # screen (once for each time the login screen is built), and what it said in this boot.
        self.prompt_says = [_place_line()] if prompt_says is None else list(prompt_says)
        self.said, self.looked, self.journal_exit, self.pictures, self.clock = [], False, journal_exit, [], clock
        self.watcher, self.stop_after, self.on_since = watcher, stop_after, None
        self.addon_confirm_after, self.update_keeps_token = addon_confirm_after, update_keeps_token
        self.addon_changed = self.guard_trial = False
        self.guard_works, self.glass_draws, self.guard_too_eager = guard_works, glass_draws, guard_too_eager
        self.confirm_after, self.path_state, self.confirm_at = confirm_after, path_state, None
        self.boot, self.silent, self.cmds = "boot-1", 0, []
        self.state, self.token, self.stopped, self.values = "off", "", "", None
        self.note, self.glass, self.broken, self.removed = None, False, False, False
        self.logged_in, self.typed, self.boots, self.n = False, "", 0, 0
        self.family, self.gdm_unit = "fedora", "gdm.service"
        self.qmp = _FakeQmp(self)
        self.greeter_start()

    # the login screen
    def greeter_start(self):
        self.glass = self.looked = False
        if self.state in ("trial", "on") and not self.removed:
            if self.note and self.note["phase"] == "starting" and self.note["token"] == self.token:
                self.note = {**self.note, "phase": "safe", "boot": self.boot}
            elif self.broken:
                self.note = {"v": 1, "token": self.token, "boot": self.boot, "phase": "error", "verified": ""}
            else:
                self.note = {"v": 1, "token": self.token, "boot": self.boot, "phase": "ok", "verified": ""}
                self.glass = self.glass_draws

    def key(self, keys):
        if keys == ["ret"] and self.typed == lb.PASSWORD:
            self.logged_in, self.typed = True, ""
            if self.state == "trial" and self.note and self.note["phase"] == "ok":
                delay = self.addon_confirm_after if self.guard_trial else self.confirm_after
                self.confirm_at = lb.time.monotonic() + delay
        elif keys == ["ret"]:
            self.typed = ""
            if self.glass and not self.looked:              # the prompt shows: the add-on looks at its place
                self.looked = True
                self.said += [(lb.time.time(), line) for line in self.prompt_says]

    def type_text(self, text):
        self.typed += text

    def wake_screen(self):
        pass

    def picture(self, name):
        self.pictures.append(name)
        colour = bytes([230, 120, 60]) if self.glass else bytes([40, 40, 40])
        return lb.Picture(64, 40, colour * 64 * 40)

    def serial_tail(self, n=1):
        return "login: "

    def boot_id(self):
        return self.boot

    def reboot(self, label):
        self.logged_in = False
        self.said = []                                      # journalctl -b: this boot only
        self.boot = f"boot-{int(self.boot.split('-')[1]) + 1}"
        if self.addon_changed and self.state == "on":
            # The add-on's files changed: the guard starts a new trial in this boot.
            self.addon_changed, self.guard_trial = False, True
            self.state, self.boots, self.stopped = "trial", 1, ""
            if not self.update_keeps_token:
                self.n += 1
                self.token = f"{self.n:032x}"
            self.greeter_start()
            return
        if self.state == "on" and self.guard_too_eager:
            self.state, self.stopped, self.silent = "off", "silent", 1
        if self.state == "trial" and self.guard_works:
            if self.note and self.note["token"] == self.token and self.note["phase"] in ("safe", "error"):
                self.state, self.stopped = "off", "crash"
            else:
                self.boots += 1
                if self.boots >= 2:
                    self.state, self.stopped = "off", "no-login"
        self.greeter_start()

    # what the lane asks
    def sh(self, cmd, check=True, input=None, timeout=300, quiet=False):
        self.cmds.append(cmd)
        out, code = "", 0
        js = f"{lb.ADDON_DIR}/login.js"
        if self.confirm_at is not None and lb.time.monotonic() >= self.confirm_at:
            self.state, self.confirm_at, self.on_since = "on", None, lb.time.monotonic()
        if cmd == f"{lb.HELPER} status":
            out = json.dumps({"version": 1, "available": True, "why": "", "state": self.state, "stopped": self.stopped,
                              "values": self.values, "picture_sha256": ""})
        elif cmd == f"systemctl show -p Result,ExecMainStatus,ConditionResult,ExecMainStartTimestampMonotonic {lb.GUARD}":
            out = ("Result=success\nExecMainStatus=0\nConditionResult=" + self.guard_condition +
                   "\nExecMainStartTimestampMonotonic=" + ("1234" if self.guard_condition == "yes" else "0"))
        elif cmd == "sudo cat /var/lib/fedora-glass/login/state.json":
            out = json.dumps({"silent_boots": self.silent, "route": "a", "db": "gdm",
                              "trial_boots": self.boots}) if self.state != "off" else ""
        elif cmd == f"systemctl show -p Id,ActiveState,SubState,Result {lb.CHECK_PATH} {lb.CHECK_SERVICE}":
            path = self.path_state
            if path != "failed" and self.state == "on" and (self.watcher == "stops" or (self.watcher == "stays-after-update" and not self.guard_trial)) and self.on_since is not None \
                    and lb.time.monotonic() - self.on_since >= self.stop_after:
                path = "inactive"
            out = (f"Id={lb.CHECK_PATH}\nActiveState={path}\nSubState=x\nResult=success\n\n"
                   f"Id={lb.CHECK_SERVICE}\nActiveState=inactive\nSubState=dead\nResult=success")
        elif cmd.startswith("for f in /etc/dconf/profile/gdm"):
            out = "== /etc/dconf/profile/gdm\nuser-db:user\nsystem-db:gdm"
        elif cmd == "date +%s":
            out, code = (str(int(lb.time.time())), 0) if self.clock else ("", 255)
        elif cmd.startswith("sudo journalctl -b _COMM=gnome-shell") and cmd.endswith(" --no-pager -o cat"):
            since = re.search(r'--since "@(\d+)"', cmd)                 # without it: all of this boot
            out = "\n".join(self.shell_journal + [line for at, line in self.said if not since or at >= int(since[1])])
            code = self.journal_exit
            if code:
                out = ""
        elif cmd.startswith("sudo journalctl -b -u gdm.service -u gdm3.service --since"):
            n, self.gdm_pending = self.gdm_pending, 0
            out = "\n".join(
                [f"Nov 13 10:00:0{i}.123456 glass-test gdm[1]: Gdm: GdmDisplay: Session never registered, failing" for i in range(n)]
                + (["Nov 13 10:00:05.000000 glass-test gdm-launch-environment]: pam_unix(gdm-launch-environment:session): "
                    "session opened for user gdm-greeter-2(uid=60579) by (uid=0)"] if n else []))
        elif "journalctl" in cmd:
            out = "Nov 13 JOURNAL LINE"
        elif cmd == "sudo cat /etc/fedora-glass/login/look.json":
            out = json.dumps({"version": 1, "token": self.token}) if self.state != "off" else ""
        elif cmd.startswith(f"sudo {lb.HELPER} on '"):
            values = json.loads(cmd.split("'")[1])
            if values.get("picture") == "wallpaper":
                assert input and input[:3] == b"\xff\xd8\xff"
            if self.state == "off":
                self.n += 1
                self.state, self.token, self.stopped, self.boots = "trial", f"{self.n:032x}", "", 0
                self.guard_trial = False
            self.values = values
        elif cmd in (f"sudo {lb.HELPER} off", "sudo fedora-glass login-screen off"):
            self.state, self.values = "off", None
        elif cmd in ("sudo systemctl restart gdm.service", "sudo systemctl start gdm.service"):
            self.logged_in = False
            self.greeter_start()
        elif cmd == "sudo systemctl stop gdm.service":
            self.logged_in = False
            if self.note and self.note["phase"] == "starting":
                self.note = {**self.note, "phase": "ok"}
        elif cmd == f"sudo loginctl terminate-user {lb.USER}":
            self.logged_in = False
        elif cmd.startswith("sudo sh -c 'echo") and "extension.js" in cmd:
            self.addon_changed = True
        elif cmd.startswith("sudo sh -c 'printf"):
            assert "boot test" in cmd and js in cmd
            self.broken = True
        elif cmd.startswith("sudo cp -a /root/lgv-login.js.saved"):
            self.broken = False
        elif cmd.startswith("sudo dnf -y -q remove"):
            self.removed, self.state = True, "off"
        r = subprocess.CompletedProcess(cmd, code, out.encode(), b"")
        r.out, r.err = out, "Failed to open the journal" if code else ""
        return r

    def probe(self, *args):
        if args == ("sessions",):
            s = [{"id": "c1", "user": "gdm-greeter", "uid": 60578, "class": "greeter", "type": "wayland",
                  "state": "active", "gnome_shell": True},
                 {"id": "2", "user": "tester", "uid": 1000, "class": "user", "type": "tty", "state": "active",
                  "gnome_shell": False}]
            if self.logged_in:
                s.append({"id": "5", "user": "tester", "uid": 1000, "class": "user", "type": "wayland",
                          "state": "active", "gnome_shell": True})
            return {"sessions": s}
        if args == ("health",):
            return {"note": self.note}
        if args == ("write-health", "starting"):
            self.note = {"v": 1, "token": self.token, "phase": "starting", "verified": ""}
            return {"path": "/var/lib/gdm/seat0/state/fedora-glass-login/health.json", "note": self.note, "owner": "60578:65534"}
        on = self.state != "off" and not self.removed
        if args == ("dconf-state",):
            exts = f"['{lb.UUID}']" if on else "@as []"
            etc = [{"path": ".", "kind": "d", "mode": "0o755", "owner": "0:0"}]
            if on or (self.removed and self.leaves_a_lock):
                etc.append({"path": "db/gdm.d/50-fedora-glass", "kind": "f", "mode": "0o644", "owner": "0:0", "sha256": "x"})
            return {"gsettings": {"org.gnome.shell enabled-extensions": exts}, "dump": exts, "etc": etc}
        if args == ("denials",):
            return {"selinux": "Enforcing", "apparmor": "", "lines": []}
        if args == ("ours",):
            return {"dconf_files": ["/etc/dconf/db/gdm.d/50-fedora-glass"] if on else [], "etc_login": on, "var_login": on}
        raise AssertionError(args)


def _lane(monkeypatch, tmp_path, guest):
    monkeypatch.setattr(lb, "time", _Clock())
    lane = lb.Lane(guest, tmp_path)
    return lane


def test_every_step_passes_on_a_pc_that_keeps_the_contract(monkeypatch, tmp_path, capsys):
    guest = _FakeGuest()
    lane = _lane(monkeypatch, tmp_path, guest)
    assert lane.run(lb.plan()), lane.notes
    assert set(lane.results.values()) == {"PASS"}
    out = capsys.readouterr().out
    assert "----- BEGIN PNG 01-plain (64x40) -----" in out and "----- BEGIN PNG 02-glass (64x40) -----" in out
    assert out.count("PASS step") == 12
    assert "silent_boots: 0" in out and out.count("the boot guard ran in this boot and succeeded") == 2
    assert guest.cmds.count(f"sudo journalctl -b -u {lb.GUARD} --no-pager") == 2
    assert not any("systemd-analyze" in c for c in guest.cmds)        # only printed on a failure
    assert json.loads((tmp_path / "results.json").read_text())["results"]["removal"] == "PASS"


def test_a_guard_that_never_switches_off_fails_the_lockout_steps(monkeypatch, tmp_path, capsys):
    lane = _lane(monkeypatch, tmp_path, _FakeGuest(guard_works=False))
    assert not lane.run(lb.plan())
    assert {s: r for s, r in lane.results.items() if r != "PASS"} == {"crash": "FAIL", "broken-addon": "FAIL", "no-login": "FAIL"}
    assert "stopped = crash" in lane.notes["crash"] and "stopped = no-login" in lane.notes["no-login"]
    out = capsys.readouterr().out
    assert out.count("----- BEGIN PNG fail-") == 1                  # only the first failure in the log
    assert "--- what the VM looked like when crash failed ---" in out


def test_glass_that_does_not_draw_fails_its_step_and_skips_what_builds_on_it(monkeypatch, tmp_path):
    lane = _lane(monkeypatch, tmp_path, _FakeGuest(glass_draws=False))
    assert not lane.run(lb.plan())
    assert lane.results["glass"] == "FAIL" and "differs clearly" in lane.notes["glass"]
    assert lane.results["login"] == "SKIP" and lane.results["update"] == "SKIP" and lane.results["restart"] == "SKIP"
    assert lane.results["off"] == "PASS" and lane.results["removal"] == "PASS"


def test_a_guard_that_turns_the_glass_off_on_a_plain_reboot_fails_restart(monkeypatch, tmp_path, capsys):
    guest = _FakeGuest(guard_too_eager=True)
    lane = _lane(monkeypatch, tmp_path, guest)
    assert not lane.run(lb.plan())
    assert {s: r for s, r in lane.results.items() if r != "PASS"} == {"restart": "FAIL", "addon-update": "SKIP"}
    assert "still on with nothing stopped" in lane.notes["restart"] and "'silent'" in lane.notes["restart"]
    assert f"systemd-analyze security {lb.GUARD} | tail -3" in guest.cmds
    assert f"sudo journalctl -b -u {lb.GUARD} --no-pager -n 200" in guest.cmds
    assert "----- BEGIN PNG fail-restart" in capsys.readouterr().out


def test_a_removal_that_leaves_a_file_under_etc_dconf_fails_the_removal_step(monkeypatch, tmp_path):
    lane = _lane(monkeypatch, tmp_path, _FakeGuest(leaves_a_lock=True))
    assert not lane.run(lb.plan())
    assert lane.results["removal"] == "FAIL" and "/etc/dconf is as it was" in lane.notes["removal"]


def test_a_guard_that_did_not_run_this_boot_fails_restart_although_systemd_says_success(monkeypatch, tmp_path):
    lane = _lane(monkeypatch, tmp_path, _FakeGuest(guard_condition="no"))
    assert not lane.run(lb.plan())
    assert lane.results["restart"] == "FAIL" and "the boot guard ran in this boot" in lane.notes["restart"]


# ---- L1: a download that ends early carries on with a Range request -----------------------------

import hashlib
import http.server
import threading

PAYLOAD = bytes(range(256)) * 4096 + b"tail"          # about 1 MiB, with an odd end


def _serve(mode, cut=300_000):
    """A server on 127.0.0.1 for PAYLOAD. mode "short": the first plain request promises everything
    but stops after `cut` bytes, a Range request is honoured (206). "no-range": same, but Range is
    ignored (200 with the whole body). "always-short": every answer stops early."""
    seen = []

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            rng = self.headers.get("Range")
            seen.append(rng)
            if rng and mode == "short":
                start = int(re.fullmatch(r"bytes=(\d+)-", rng).group(1))
                body = PAYLOAD[start:]
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {start}-{len(PAYLOAD) - 1}/{len(PAYLOAD)}")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(PAYLOAD)))
            self.end_headers()
            short = mode == "always-short" or not seen[:-1]
            self.wfile.write(PAYLOAD[:cut] if short else PAYLOAD)
            self.wfile.flush()
            self.close_connection = True

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, seen


@pytest.mark.parametrize("mode", ["short", "no-range"])
def test_fetch_resumes_a_short_body_and_hashes_every_byte_once(tmp_path, capsys, mode):
    srv, seen = _serve(mode)
    try:
        dest = tmp_path / "image"
        got = lb.fetch(f"http://127.0.0.1:{srv.server_port}/image.qcow2", dest, pause=0)
    finally:
        srv.shutdown()
    assert dest.read_bytes() == PAYLOAD
    assert got == hashlib.sha256(PAYLOAD).hexdigest()
    assert seen[0] is None and seen[1] == "bytes=300000-"
    out = capsys.readouterr().out
    if mode == "short":
        assert "image.qcow2: the body ended after 300000 of 1048580 bytes; resuming at byte 300000 (resume 1 of 5)" in out
    else:
        assert "answered 200 to a Range request, starting again from zero" in out


def test_fetch_of_small_files_returns_the_complete_bytes_too(tmp_path):
    srv, seen = _serve("short", cut=1000)
    try:
        data = lb.fetch(f"http://127.0.0.1:{srv.server_port}/CHECKSUM", pause=0)
    finally:
        srv.shutdown()
    assert data == PAYLOAD


def test_fetch_gives_up_after_five_resumes_and_never_returns_a_cut_file(tmp_path):
    srv, seen = _serve("always-short")
    try:
        with pytest.raises(RuntimeError, match="after 5 resumes"):
            lb.fetch(f"http://127.0.0.1:{srv.server_port}/image", tmp_path / "image", pause=0)
    finally:
        srv.shutdown()
    assert len(seen) == 6


# ---- L2: mirror first, master second; L3: the signing key is pinned ---------------------------------

def test_fedora_image_is_tried_from_the_redirector_then_the_master():
    index = lb.fedora_index_urls("45")[0]
    assert lb.fedora_image_urls(index, "I.qcow2") == [
        "https://download.fedoraproject.org/pub/fedora/linux/releases/45/Cloud/x86_64/images/I.qcow2",
        "https://dl.fedoraproject.org/pub/fedora/linux/releases/45/Cloud/x86_64/images/I.qcow2"]


def _info(urls, sha):
    return {"urls": urls, "url": urls[0], "name": "img", "sha256": sha}


def test_a_bad_mirror_is_logged_and_the_master_is_used(monkeypatch, tmp_path, capsys):
    good = b"the real image"
    tried = []

    def fake_fetch(url, dest=None, **kw):
        tried.append(url)
        data = b"tampered" if "mirror" in url else good
        dest.write_bytes(data)
        return hashlib.sha256(data).hexdigest()
    monkeypatch.setattr(lb, "fetch", fake_fetch)
    dest = tmp_path / "img"
    lb.download_checked(_info(["https://mirror/img", "https://master/img"], hashlib.sha256(good).hexdigest()), dest)
    assert tried == ["https://mirror/img", "https://master/img"] and dest.read_bytes() == good
    assert "https://mirror/img did not give a good image" in capsys.readouterr().out


def test_a_mirror_that_fails_to_connect_falls_back_and_only_both_failing_fails_the_run(monkeypatch, tmp_path):
    def broken_mirror(url, dest=None, **kw):
        if "mirror" in url:
            raise OSError("connection reset")
        dest.write_bytes(b"x")
        return hashlib.sha256(b"x").hexdigest()
    monkeypatch.setattr(lb, "fetch", broken_mirror)
    lb.download_checked(_info(["https://mirror/img", "https://master/img"], hashlib.sha256(b"x").hexdigest()), tmp_path / "a")
    with pytest.raises(RuntimeError, match="no source gave an image") as e:
        lb.download_checked(_info(["https://mirror/img", "https://master/img"], "0" * 64), tmp_path / "b")
    assert "mirror/img" in str(e.value) and "master/img" in str(e.value)
    assert not (tmp_path / "b").exists()                  # a file that did not match is not left lying about


def test_fedora_signing_keys_are_pinned_and_a_wrong_key_is_refused():
    assert lb.FEDORA_KEYS == {"44": "36F612DCF27F7D1A48A835E4DBFCF71C6D9F90A6",
                              "45": "4F50A6114CD5C6976A7F1179655A4B02F577861E"}
    lb.check_fedora_signer("45", lb.FEDORA_KEYS["45"], ["Fedora (45) <fedora-45-primary@fedoraproject.org>"])
    # Another Fedora key with a Fedora uid (44's for 45) and a stranger's key with a faked uid:
    for primary, uids in ((lb.FEDORA_KEYS["44"], ["Fedora (45) <fedora-45-primary@fedoraproject.org>"]),
                          ("A" * 40, ["Fedora (45) <fedora-45-primary@fedoraproject.org>"])):
        with pytest.raises(RuntimeError, match="not Fedora 45's key"):
            lb.check_fedora_signer("45", primary, uids)
    with pytest.raises(RuntimeError, match="not Fedora 45's"):      # the right key but the wrong uid
        lb.check_fedora_signer("45", lb.FEDORA_KEYS["45"], ["Fedora (44) <fedora-44-primary@fedoraproject.org>"])
    with pytest.raises(RuntimeError, match="no pinned"):
        lb.check_fedora_signer("46", "A" * 40, ["Fedora (46)"])


class _FakeGpg:
    primary = lb.FEDORA_KEYS["45"]

    def __init__(self, work):
        pass

    def keyring(self, sources, name):
        return Path(name)

    def verify(self, ring, signed, sig=None, plain_out=None):
        plain_out.write_text("SHA256 (Fedora-Cloud-Base-Generic-45-1.4.x86_64.qcow2) = " + "ab" * 32 + "\n")
        return {"good": True, "fpr": self.primary, "primary": self.primary}

    def uids(self, ring):
        return {self.primary: ["Fedora (45) <fedora-45-primary@fedoraproject.org>"]}


def _find_fedora(monkeypatch, tmp_path, primary):
    asked = []

    def fake_fetch(url, dest=None, **kw):
        asked.append(url)
        if url.endswith("/images/"):
            return b'<a href="Fedora-Cloud-Base-Generic-45-1.4.x86_64.qcow2">x</a><a href="Fedora-Cloud-45-1.4-x86_64-CHECKSUM">c</a>'
        return b"data"
    monkeypatch.setattr(lb, "fetch", fake_fetch)
    monkeypatch.setattr(lb, "Gpg", type("G", (_FakeGpg,), {"primary": primary}))
    return lb.find_image("fedora-45", tmp_path), asked


def test_find_image_takes_the_signed_lists_from_the_master_only(monkeypatch, tmp_path):
    info, asked = _find_fedora(monkeypatch, tmp_path, lb.FEDORA_KEYS["45"])
    assert all(u.startswith("https://dl.fedoraproject.org/") or u == lb.FEDORA_KEYRING_URL for u in asked)
    assert info["urls"][0].startswith("https://download.fedoraproject.org/")
    assert info["urls"][1].startswith("https://dl.fedoraproject.org/") and info["sha256"] == "ab" * 32


def test_find_image_refuses_a_checksum_signed_by_any_other_key(monkeypatch, tmp_path):
    with pytest.raises(RuntimeError, match="not Fedora 45's key"):
        _find_fedora(monkeypatch, tmp_path, lb.FEDORA_KEYS["44"])


# ---- L4, L6: how the trial ended, and which dconf route ---------------------------------------------

def test_login_step_logs_the_trial_watch_units_and_the_time_to_confirm(monkeypatch, tmp_path, capsys):
    guest = _FakeGuest(confirm_after=4)
    lane = _lane(monkeypatch, tmp_path, guest)
    assert lane.run(["baseline", "on", "glass", "login"])
    out = capsys.readouterr().out
    assert re.search(r"the state became on [3-5] s after the login \(limit 20 s\)", out)
    assert f"systemctl show -p Id,ActiveState,SubState,Result {lb.CHECK_PATH} {lb.CHECK_SERVICE}" in guest.cmds
    assert re.search(r"waited [1-3] s for .*check.path to stop", out)
    assert f"sudo journalctl -b -u {lb.CHECK_PATH} -u {lb.CHECK_SERVICE} --no-pager -n 40" in guest.cmds


def test_login_step_fails_when_the_trial_is_confirmed_late_but_says_how_late(monkeypatch, tmp_path, capsys):
    lane = _lane(monkeypatch, tmp_path, _FakeGuest(confirm_after=35))
    assert not lane.run(["baseline", "on", "glass", "login"])
    assert lane.results["login"] == "FAIL" and "within 20 s" in lane.notes["login"]
    assert re.search(r"the state became on 3[5-7] s after the login", capsys.readouterr().out)


def test_login_step_fails_when_the_path_unit_is_failed_even_if_the_trial_was_confirmed(monkeypatch, tmp_path, capsys):
    lane = _lane(monkeypatch, tmp_path, _FakeGuest(path_state="failed"))
    assert not lane.run(["baseline", "on", "glass", "login"])
    assert lane.results["login"] == "FAIL" and f"{lb.CHECK_PATH} is not failed (ActiveState failed" in lane.notes["login"]
    assert "within 20 s" not in lane.notes["login"]


def test_login_step_reports_both_problems_when_both_happen(monkeypatch, tmp_path):
    lane = _lane(monkeypatch, tmp_path, _FakeGuest(confirm_after=50, path_state="failed"))
    assert not lane.run(["baseline", "on", "glass", "login"])
    assert "within 20 s" in lane.notes["login"] and "is not failed" in lane.notes["login"]


def test_parse_show_blocks_by_unit_id():
    text = "Id=a.path\nActiveState=failed\nResult=start-limit-hit\n\nId=a.service\nActiveState=inactive\n"
    assert lb.parse_show_blocks(text) == {"a.path": {"Id": "a.path", "ActiveState": "failed", "Result": "start-limit-hit"},
                                          "a.service": {"Id": "a.service", "ActiveState": "inactive"}}


# ---- where the password prompt stands under the glass card, in the add-on's own words --------------

# The lines as the add-on writes them (tests/js/login-prompt-place.test.mjs asserts these very
# lines, so the add-on and this lane cannot drift apart unseen): GNOME 51.1 at 1080 px, a layout
# that takes no notice of the margin, and a prompt that got GNOME's own place back.
PLACE_LINE = ("Fedora Glass login: the prompt stands 415 px down the screen, wanted 415 "
              "(249 px tall, margin 201, set again: 0, at first: 0 px off, way: offset, screen: 1080 px, scale: 1, text: 1)")
STUCK_LINE = ("Fedora Glass login: the prompt stands 315 px down the screen, wanted 415, and does not follow the margin "
              "(249 px tall, margin 201, set again: 2, at first: -100 px off, way: offset, screen: 1080 px, scale: 1, text: 1)")
OWN_LINE = ("Fedora Glass login: the prompt has GNOME's own place: with ours it would end below the screen "
            "(margin 201, set again: 0, at first: 0 px off, screen: 864 px)")
LOGIN = ["baseline", "on", "glass", "login"]


def _place_line(top=306, wanted=306, stuck=False, again=0, first=None):
    first = top - wanted if first is None else first
    return (f"Fedora Glass login: the prompt stands {top} px down the screen, wanted {wanted}"
            f"{', and does not follow the margin' if stuck else ''} (262 px tall, margin 256, set again: {again}, "
            f"at first: {first} px off, way: offset, screen: 800 px, scale: 1, text: 1.25)")


def test_the_prompts_place_is_read_from_the_lines_the_addon_writes():
    js_test = (ROOT / "tests" / "js" / "login-prompt-place.test.mjs").read_text()
    login_js = (ROOT / "fedoraglass" / "data" / "login-extension" / lb.UUID / "login.js").read_text()

    def pinned(begins):                                    # a line the JS test asserts, put together again
        at = js_test.index(begins)
        return "".join(re.findall(r"'((?:[^'\\]|\\.)*)'", js_test[at - 1:at + 400])[:2])
    assert pinned("Fedora Glass login: the prompt stands 415") == PLACE_LINE
    assert pinned("Fedora Glass login: the prompt stands 315") == STUCK_LINE
    assert pinned("Fedora Glass login: the prompt has GNOME\\'s own place: with ours it would end below the screen ' +\n"
                  "        '(margin 201").replace("\\'", "'") == OWN_LINE
    assert ("console.log('Fedora Glass login: the prompt has GNOME\\'s own place: with ours it would end below the screen ' +\n"
            "            `(margin ${margin}, set again: ${this._placeTries}, at first: ${first}, screen: ${m.height} px)`);") in login_js
    assert "the prompt stands ${top} px down the screen, wanted ${wanted}" in login_js
    # Every line of the add-on on the prompt begins as the lane expects, so none can be missed.
    assert set(re.findall(r"console\.log\([`'](Fedora Glass login: the prompt )", login_js)) == {lb._PROMPT_SAID}
    assert len(re.findall(r"console\.log\([`']Fedora Glass login: the prompt ", login_js)) == 2

    journal = "\n".join(["GNOME Shell started at Sat Nov 28 2026", PLACE_LINE, "something else", STUCK_LINE,
                         "GNOME Shell-Message: 03:49:23.725: " + _place_line(320, 306, stuck=True, again=4, first=30),
                         OWN_LINE])
    (first, stuck, last, own), unread = lb.prompt_places(journal)
    assert unread == []
    assert first == {"top": 415, "wanted": 415, "tall": 249, "margin": 201, "again": 0, "first": 0, "screen": 1080,
                     "way": "offset", "scale": 1.0, "text": 1.0, "follows": True, "own": False, "off": 0,
                     "middle": -0.5, "aim": -0.5}
    assert (stuck["off"], stuck["first"], stuck["follows"], stuck["again"], stuck["aim"]) == (-100, -100, False, 2, -0.5)
    assert (last["off"], last["first"], last["follows"], last["again"], last["text"], last["middle"], last["aim"]) == (
        14, 30, False, 4, 1.25, 51.0, 37.0)
    assert own == {"own": True, "said": OWN_LINE}
    assert lb.prompt_places("") == ([], [])
    # A line of the add-on's that this cannot read is never taken for nothing said.
    old = PLACE_LINE.replace(", at first: 0 px off", "")
    assert lb.prompt_places(f"one\n{old}\nFedora Glass login: the prompt stands somewhere\n{PLACE_LINE}") == (
        [first], [old, "Fedora Glass login: the prompt stands somewhere"])


def test_the_lane_says_in_words_where_the_addon_aims():
    place = lambda line: lb.prompt_places(line)[0][0]
    assert lb.aim_text(place(PLACE_LINE)) == "the screen's middle"
    assert lb.aim_text(place(_place_line())) == "37 px under the screen's middle (room for the big clock above it)"
    low = _place_line().replace("margin 256", "margin 0")
    assert lb.aim_text(place(low)) == "37 px under the screen's middle (no margin of the add-on's can lift it higher)"
    assert lb.aim_text(place(_place_line(200, 200))) == "69 px above the screen's middle (it never means to)"


def test_login_step_says_where_the_prompt_stood_and_shows_its_picture(monkeypatch, tmp_path, capsys):
    guest = _FakeGuest(prompt_says=[_place_line(306, 305, again=1, first=5)])
    lane = _lane(monkeypatch, tmp_path, guest)
    assert lane.run(LOGIN)
    out = capsys.readouterr().out
    assert "----- BEGIN PNG login-prompt-1 (64x40) -----" in out
    assert ("the password prompt: 306 px down the screen, wanted 305 (+1 px), 262 px tall, its middle +37 px from the "
            "screen's middle; margin 256, set again 1×, at first +5 px off, GNOME's way offset, screen 800 px, scale 1, "
            "text 1.25") in out
    assert "the add-on aims at 36 px under the screen's middle (room for the big clock above it)" in out
    assert "gnome-shell journal since the step began: 1 lines, 0 of them errors of the add-on" in out
    for said in ("ok   no error of the add-on in the login screen's journal",
                 "ok   every line of the add-on on the prompt's place can be read (0 cannot)",
                 "ok   the add-on said where the password prompt stands",
                 "ok   GNOME places the password prompt as the add-on expects (at the first look +5 px from where the "
                 "glass card wants it, at most 8)",
                 "ok   the password prompt stands where the glass card wants it (+1 px, at most 4)"):
        assert said in out, said
    # Set again stands out in the Note column; a prompt in its place at the first look reads otherwise.
    note = "prompt +1 px from its place after 1× set again (at first +5 px)"
    assert lane.notes["login"] == note
    assert f"| 4. login | PASS | {note} |" in lb.summary("fedora-45", lb.plan(), lane.results, lane.notes)
    plain = _lane(monkeypatch, tmp_path, _FakeGuest())
    assert plain.run(LOGIN) and plain.notes["login"] == "prompt +0 px from its place at the first look"


def test_login_step_fails_when_the_prompt_stands_far_from_where_the_card_wants_it(monkeypatch, tmp_path, capsys):
    lane = _lane(monkeypatch, tmp_path, _FakeGuest(prompt_says=[PLACE_LINE, _place_line(320, 306, stuck=True, again=4)]))
    assert not lane.run(LOGIN)
    assert lane.results["login"] == "FAIL"
    assert lane.notes["login"] == (
        "GNOME places the password prompt as the add-on expects (at the first look +14 px from where the glass card "
        "wants it, at most 8); the password prompt stands where the glass card wants it (+14 px, at most 4)")
    out = capsys.readouterr().out
    assert "GNOME took no notice of the margin" in out and out.count("the password prompt: ") == 2    # both builds are shown


def test_a_prompt_the_addon_had_to_set_right_from_far_off_fails_although_it_stands_right_now(monkeypatch, tmp_path):
    # This GNOME, or its login theme, places the prompt in a way the add-on does not know: it
    # set the place right by itself, but a user saw the card and the clock move once.
    lane = _lane(monkeypatch, tmp_path, _FakeGuest(prompt_says=[_place_line(306, 306, again=1, first=-74)]))
    assert not lane.run(LOGIN)
    assert lane.notes["login"] == ("GNOME places the password prompt as the add-on expects (at the first look -74 px "
                                   "from where the glass card wants it, at most 8)")
    # A font or a theme that sizes the prompt a little otherwise is no failure, and it is said.
    near = _lane(monkeypatch, tmp_path, _FakeGuest(prompt_says=[_place_line(306, 306, again=1, first=-8)]))
    assert near.run(LOGIN)
    assert near.notes["login"] == "prompt +0 px from its place after 1× set again (at first -8 px)"


def test_a_prompt_that_does_not_follow_but_stands_close_passes_and_says_so(monkeypatch, tmp_path):
    lane = _lane(monkeypatch, tmp_path, _FakeGuest(prompt_says=[_place_line(303, 306, stuck=True, again=4)]))
    assert lane.run(LOGIN)
    assert lane.notes["login"] == "prompt -3 px from its place after 4× set again (at first -3 px), margin not followed"


def test_a_late_trial_and_a_prompt_out_of_place_are_both_reported(monkeypatch, tmp_path, capsys):
    guest = _FakeGuest(confirm_after=35, prompt_says=[_place_line(320, 306, stuck=True, again=4)])
    lane = _lane(monkeypatch, tmp_path, guest)
    assert not lane.run(LOGIN)
    assert "within 20 s" in lane.notes["login"] and "(+14 px, at most 4)" in lane.notes["login"]
    assert "the password prompt: 320 px down the screen" in capsys.readouterr().out      # read although the trial was late


def test_an_addon_that_says_nothing_about_the_prompt_fails_the_login_step(monkeypatch, tmp_path, capsys):
    # The user logged in, so the field was there to look at: an add-on that never looked, or
    # looks no more since a change, must not pass for one whose prompt stands right.
    lane = _lane(monkeypatch, tmp_path, _FakeGuest(prompt_says=[]))
    assert not lane.run(LOGIN)
    assert lane.notes["login"] == "the add-on said where the password prompt stands"
    out = capsys.readouterr().out
    assert "FAIL the add-on said where the password prompt stands" in out
    assert "gnome-shell journal since the step began: 0 lines" in out


def test_a_line_on_the_prompt_that_the_lane_cannot_read_fails_the_login_step(monkeypatch, tmp_path, capsys):
    old = PLACE_LINE.replace(", at first: 0 px off", "")          # the add-on's line changed, the lane's reading did not
    lane = _lane(monkeypatch, tmp_path, _FakeGuest(prompt_says=[old]))
    assert not lane.run(LOGIN)
    assert lane.notes["login"] == "every line of the add-on on the prompt's place can be read (1 cannot)"
    out = capsys.readouterr().out
    assert f"the add-on says, and this cannot read it: {old}" in out
    assert "ok   the add-on said where the password prompt stands" in out
    # ...also next to a line it can read: that one is still judged, and the step still fails.
    both = _lane(monkeypatch, tmp_path, _FakeGuest(prompt_says=[_place_line(), old]))
    assert not both.run(LOGIN)
    assert both.notes["login"] == "every line of the add-on on the prompt's place can be read (1 cannot)"


def test_a_journal_that_could_not_be_read_fails_the_step_instead_of_passing_for_a_clean_one(monkeypatch, tmp_path, capsys):
    guest = _FakeGuest()
    lane = _lane(monkeypatch, tmp_path, guest)
    assert lane.run(["baseline", "on", "glass"])
    guest.journal_exit = 1
    assert not lane.run(["login"])
    assert lane.notes["login"] == "GNOME Shell's journal could be read (journalctl exited 1)"
    assert "Failed to open the journal" in capsys.readouterr().out
    # The same in a step that only looks for errors of the add-on.
    glass = _lane(monkeypatch, tmp_path, _FakeGuest(journal_exit=255))
    assert not glass.run(["baseline", "on", "glass"])
    assert glass.notes["glass"] == "GNOME Shell's journal could be read (journalctl exited 255)"


def test_a_prompt_that_got_gnomes_own_place_back_fails_the_step_on_these_screens(monkeypatch, tmp_path, capsys):
    # These VMs have GNOME's own login theme and room for the card: the add-on gives the place
    # back only when its sums went wrong. It can do so before it ever said a place, so the line
    # on its own must fail, or a GNOME that places the prompt in a new way would pass here.
    lane = _lane(monkeypatch, tmp_path, _FakeGuest(prompt_says=[OWN_LINE]))
    assert not lane.run(LOGIN)
    assert lane.notes["login"] == ("the password prompt keeps the glass card's place (the add-on gave it GNOME's own back 1×: "
                                   "with the card's it would end below the screen)")
    out = capsys.readouterr().out
    assert f"the password prompt: GNOME's own place. {OWN_LINE}" in out            # with what the add-on had tried
    assert "ok   the add-on said where the password prompt stands" in out
    # After a place of the card's: that place no longer holds, so only its first look is judged.
    after = _lane(monkeypatch, tmp_path, _FakeGuest(prompt_says=[_place_line(320, 306, stuck=True, again=4, first=3), OWN_LINE]))
    assert not after.run(LOGIN)
    assert "gave it GNOME's own back 1×" in after.notes["login"] and "at most 4)" not in after.notes["login"]
    assert "at most 8)" not in after.notes["login"]                                 # +3 px at the first look is fine
    # Before one (the login screen was built anew): the new place is the last word and is judged.
    before = _lane(monkeypatch, tmp_path, _FakeGuest(prompt_says=[OWN_LINE, _place_line(320, 306, stuck=True, again=4, first=3)]))
    assert not before.run(LOGIN)
    assert "gave it GNOME's own back 1×" in before.notes["login"] and "(+14 px, at most 4)" in before.notes["login"]


def test_every_time_the_login_screen_was_built_counts_for_the_first_look(monkeypatch, tmp_path):
    # Built twice in the step (a screen plugged in, Large Text): the first build was far off.
    # Where the prompt stands now is fine, but a user saw the card move.
    lane = _lane(monkeypatch, tmp_path, _FakeGuest(prompt_says=[_place_line(306, 306, again=1, first=-74), _place_line()]))
    assert not lane.run(LOGIN)
    assert lane.notes["login"] == ("GNOME places the password prompt as the add-on expects (at the first look -74 px "
                                   "from where the glass card wants it, at most 8)")


def test_without_a_guest_clock_all_of_the_boots_journal_is_read_and_judged(monkeypatch, tmp_path, capsys):
    # Nothing may pass unread: a step that could not take the time reads the whole boot.
    guest = _FakeGuest(clock=False)
    lane = _lane(monkeypatch, tmp_path, guest)
    assert lane.run(LOGIN), lane.notes
    assert lane.notes["login"] == "prompt +0 px from its place at the first look"
    assert "no guest clock when the step began: all of this boot's journal of GNOME Shell is read" in capsys.readouterr().out
    assert guest.cmds.count("sudo journalctl -b _COMM=gnome-shell --no-pager -o cat") == 2          # glass and login
    silent = _lane(monkeypatch, tmp_path, _FakeGuest(clock=False, prompt_says=[]))
    assert not silent.run(LOGIN)
    assert silent.notes["login"] == "the add-on said where the password prompt stands"
    broken = _lane(monkeypatch, tmp_path, _FakeGuest(clock=False, shell_journal=["Extension fedora-glass-login@djshiye.github.io had error: boom"]))
    assert not broken.run(["baseline", "on", "glass"])
    assert broken.notes["glass"] == "no error of the add-on in the login screen's journal"


def test_an_error_of_the_addon_while_the_user_logs_in_fails_the_login_step(monkeypatch, tmp_path, capsys):
    guest = _FakeGuest()
    lane = _lane(monkeypatch, tmp_path, guest)
    assert lane.run(["baseline", "on", "glass"])
    guest.shell_journal.append("Extension fedora-glass-login@djshiye.github.io had error: boom")
    assert not lane.run(["login"])
    assert lane.notes["login"] == "no error of the add-on in the login screen's journal"
    out = capsys.readouterr().out
    assert "2 lines, 1 of them errors of the add-on" in out
    assert "ok   the password prompt stands where the glass card wants it (+0 px, at most 4)" in out   # still judged


def test_where_the_prompt_stood_is_read_even_when_the_login_did_not_work(monkeypatch, tmp_path, capsys):
    guest = _FakeGuest(prompt_says=[_place_line(320, 306, stuck=True, again=4)])
    guest.type_text = lambda text: None                    # the password never arrives: no session
    lane = _lane(monkeypatch, tmp_path, guest)
    assert not lane.run(LOGIN)
    assert lane.notes["login"].startswith("the real login did not start a wayland session for tester")
    assert "(+14 px, at most 4)" in lane.notes["login"] and "within 20 s" not in lane.notes["login"]
    out = capsys.readouterr().out
    assert "the password prompt: 320 px down the screen" in out and "the state became on" not in out
    assert guest.pictures.count("login-prompt-1") == 1 and "login-failed-2" in guest.pictures


def test_trouble_of_the_lanes_own_in_one_part_is_said_with_its_kind_and_the_other_parts_still_run(capsys):
    ran = []

    def broken():
        raise KeyError("token")
    with pytest.raises(lb.StepFailed, match=r"^KeyError: 'token'; second; third$"):
        lb.all_of(broken, lambda: ran.append(1), lambda: lb.check(False, "second"), (True, "fine"), (False, "third"))
    assert ran == [1]
    out = capsys.readouterr().out
    assert "ok   fine" in out and "FAIL second" in out and "FAIL third" in out          # every check is printed
    lb.all_of(lambda: None, (1, "truthy counts"))          # nothing wrong: nothing raised


def test_the_addon_update_step_reads_the_prompts_place_after_its_cold_boot_too(monkeypatch, tmp_path, capsys):
    guest = _FakeGuest()
    lane = _lane(monkeypatch, tmp_path, guest)
    assert lane.run(lb.plan()), lane.notes
    assert lane.notes["login"] == lane.notes["addon-update"] == "prompt +0 px from its place at the first look"
    out = capsys.readouterr().out
    assert "----- BEGIN PNG addon-update-prompt-1 (64x40) -----" in out
    assert out.count("the password prompt: 306 px down the screen") == 2          # each boot's own line, once
    # Every step's login keeps its own picture: a later one does not write over the first.
    prompts = [n for n in guest.pictures if "-prompt-" in n]
    assert prompts == ["login-prompt-1", "addon-update-prompt-1", "off-prompt-1", "crash-prompt-1",
                       "broken-addon-prompt-1", "no-login-prompt-1", "removal-prompt-1"]
    # A cold boot that places the prompt otherwise fails that step, and only that one.
    cold = _FakeGuest()
    lane = _lane(monkeypatch, tmp_path, cold)
    assert lane.run(LOGIN + ["update", "restart"])
    cold.prompt_says = [_place_line(306, 306, again=2, first=40)]
    assert not lane.run(["addon-update", "off"])
    assert lane.results["addon-update"] == "FAIL" and lane.results["off"] == "PASS"
    assert "at the first look +40 px" in lane.notes["addon-update"]


def test_step_on_says_which_dconf_route_was_taken(monkeypatch, tmp_path, capsys):
    guest = _FakeGuest()
    lane = _lane(monkeypatch, tmp_path, guest)
    assert lane.run(["baseline", "on"])
    assert lane.notes["on"] == "route a (db gdm)"
    assert "route a (db gdm)" in lb.summary("fedora-45", ["baseline", "on"], lane.results, lane.notes)
    out = capsys.readouterr().out
    assert "dconf route: a, db: gdm" in out
    assert any(c.startswith("for f in /etc/dconf/profile/gdm /usr/share/dconf/profile/gdm") for c in guest.cmds)
    assert lb.route_text("b", "fedora-glass") == "route b" and lb.route_text("", "") == "route unknown"


# ---- L5: the failure digest at the end of the log ----------------------------------------------------

def test_failure_digest_has_the_fail_lines_and_the_last_25_lines_without_bulk(monkeypatch, tmp_path, capsys):
    lane = _lane(monkeypatch, tmp_path, _FakeGuest(glass_draws=False))
    assert not lane.run(lb.plan())
    steps = lb.plan()
    d = lb.failure_digest(steps, lane.results, lane.captured)
    assert d.startswith("=== Failure digest ===\n--- step 3 glass: FAIL ---\n")
    assert re.search(r"\n\[\d\d:\d\d\]\s+FAIL the glass screen differs clearly", d)
    m = re.search(r"last (\d+) lines of the step:\n", d)
    tail = d[m.end():].splitlines()
    assert int(m.group(1)) == len(tail) <= 25 and tail[-1].endswith("FAIL step 3 glass: " + lane.notes["glass"])
    for bulk in ("JOURNAL LINE", "BEGIN PNG", "serial log", "login: "):
        assert bulk not in d.replace("serial log, last 60 lines:", "")
    assert "PASS step" not in d and "step 4" not in d      # steps that passed or were skipped are not in it
    short = lb.failure_digest(steps, lane.results, lane.captured, tail=0)
    assert "lines of the step" not in short and "FAIL the glass screen differs" in short and len(short) < 1500


def test_failure_digest_is_empty_when_all_passed(monkeypatch, tmp_path):
    lane = _lane(monkeypatch, tmp_path, _FakeGuest())
    assert lane.run(lb.plan())
    assert lb.failure_digest(lb.plan(), lane.results, lane.captured) == ""


def test_main_prints_the_digest_after_the_summary_table(monkeypatch, tmp_path, capsys):
    lane = _lane(monkeypatch, tmp_path, _FakeGuest(glass_draws=False))
    lane.run(lb.plan())
    text = lb.summary("fedora-45", lb.plan(), lane.results, lane.notes)
    assert text.index("| 3. glass | FAIL |") < len(text)
    assert "journal" not in lb.failure_digest(lb.plan(), lane.results, lane.captured).lower()


def test_failure_digest_keeps_only_the_last_25_lines_and_cuts_long_ones():
    lines = [f"[00:{i:02d}]   line {i}" for i in range(40)] + ["[00:41]   FAIL it broke " + "x" * 600]
    d = lb.failure_digest(["on", "glass"], {"on": "PASS", "glass": "FAIL"}, {"glass": lines})
    assert "last 25 lines of the step:" in d and "line 15" not in d and "line 16" in d
    assert all(len(l) <= 410 for l in d.splitlines())
    assert d.count("FAIL it broke") == 2                    # once as a FAIL line, once in the tail


# ---- the add-on update step and the removal's state folder -----------------------------------------------

def test_addon_update_starts_a_new_trial_at_boot_and_the_login_ends_it(monkeypatch, tmp_path, capsys):
    guest = _FakeGuest()
    lane = _lane(monkeypatch, tmp_path, guest)
    assert lane.run(lb.plan()), lane.notes
    assert lane.results["addon-update"] == "PASS" and lane.results["off"] == "PASS"
    assert lane.token == guest.token or guest.state == "off"
    out = capsys.readouterr().out
    assert "03-addon-update-glass" in "".join(guest.cmds) + out or "the glass still shows" in out
    ext = f"{lb.ADDON_DIR}/extension.js"
    assert f"sudo cp -a {ext} /root/lgv-extension.js.saved" in guest.cmds
    assert f"sudo cp -a /root/lgv-extension.js.saved {ext} && sudo rm -f /root/lgv-extension.js.saved" in guest.cmds
    assert f"sudo journalctl -b -u {lb.GUARD} -u {lb.CHECK_PATH} -u {lb.CHECK_SERVICE} --no-pager -n 40" in guest.cmds


def test_addon_update_fails_when_the_token_did_not_change(monkeypatch, tmp_path):
    guest = _FakeGuest(update_keeps_token=True)
    lane = _lane(monkeypatch, tmp_path, guest)
    assert not lane.run(lb.plan())
    assert {s: r for s, r in lane.results.items() if r != "PASS"} == {"addon-update": "FAIL"}
    assert "a new token" in lane.notes["addon-update"]
    assert f"sudo cp -a /root/lgv-extension.js.saved {lb.ADDON_DIR}/extension.js && sudo rm -f /root/lgv-extension.js.saved" in guest.cmds


def test_addon_update_fails_when_the_first_login_does_not_end_the_trial_in_time(monkeypatch, tmp_path):
    lane = _lane(monkeypatch, tmp_path, _FakeGuest(addon_confirm_after=35))
    assert not lane.run(lb.plan())
    assert {s: r for s, r in lane.results.items() if r != "PASS"} == {"addon-update": "FAIL"}
    assert "within 20 s" in lane.notes["addon-update"]


def test_addon_update_is_skipped_when_restart_failed_but_off_still_runs(monkeypatch, tmp_path):
    lane = _lane(monkeypatch, tmp_path, _FakeGuest(guard_too_eager=True))
    assert not lane.run(lb.plan())
    assert lane.results["restart"] == "FAIL" and lane.results["addon-update"] == "SKIP"
    assert lane.results["off"] == "PASS"


def test_removal_fails_when_root_state_folder_is_left(monkeypatch, tmp_path):
    guest = _FakeGuest()
    real = guest.probe

    def probe(*args):
        out = real(*args)
        if args == ("ours",):
            out = {**out, "var_login": True}
        return out
    guest.probe = probe
    lane = _lane(monkeypatch, tmp_path, guest)
    assert not lane.run(lb.plan())
    assert lane.results["removal"] == "FAIL" and "state folder /var/lib/fedora-glass/login is gone" in lane.notes["removal"]
    # What was left in it, and whether a check of the trial watch ran during the removal.
    assert "sudo ls -la /var/lib/fedora-glass /var/lib/fedora-glass/login 2>&1" in guest.cmds
    assert any(c.startswith("sudo journalctl -b -u fedora-glass-login-guard-check.path") for c in guest.cmds)


def test_login_step_fails_when_the_watcher_is_still_active_ten_seconds_after_the_trial_ended(monkeypatch, tmp_path, capsys):
    lane = _lane(monkeypatch, tmp_path, _FakeGuest(watcher="stays"))
    assert not lane.run(["baseline", "on", "glass", "login"])
    assert "the watcher stopped once the trial ended (ActiveState active" in lane.notes["login"]
    assert "waited 10 s for" in capsys.readouterr().out


def test_login_step_passes_when_the_watcher_stops_in_time_and_fails_when_too_late(monkeypatch, tmp_path):
    assert _lane(monkeypatch, tmp_path, _FakeGuest(stop_after=8)).run(["baseline", "on", "glass", "login"])
    assert not _lane(monkeypatch, tmp_path, _FakeGuest(stop_after=14)).run(["baseline", "on", "glass", "login"])


def test_addon_update_fails_when_the_watcher_does_not_stop(monkeypatch, tmp_path):
    lane = _lane(monkeypatch, tmp_path, _FakeGuest(watcher="stays-after-update"))
    assert not lane.run(lb.plan())
    assert {s: r for s, r in lane.results.items() if r != "PASS"} == {"addon-update": "FAIL"}
    assert "the watcher stopped once the trial ended" in lane.notes["addon-update"]


# ---- N4: errors of the add-on fail the step; GDM's retries are only reported ---------------------------------

def test_addon_errors_are_found_by_name_or_by_their_stack():
    j = "\n".join([
        "Failed to make thread 'KMS thread' high priority scheduled",                          # not ours
        "JS ERROR: TypeError: x is undefined",                                                  # ours, by its stack
        "login.js:12:3",
        f"@file:///usr/share/gdm/greeter/gnome-shell/extensions/{lb.UUID}/login.js:12:3",
        "",
        "JS ERROR: Error: another extension broke",                                            # someone else's
        "foo@resource:///org/gnome/shell/ui/x.js:1:1",
        "Extension fedora-glass-login@djshiye.github.io had error: boom",
        "fedora-glass-login: loaded fine",
        "Extension other@x had error: boom"])
    assert lb.addon_errors(j) == ["JS ERROR: TypeError: x is undefined",
                                  "Extension fedora-glass-login@djshiye.github.io had error: boom"]
    assert lb.addon_errors("") == []


def test_an_error_of_the_addon_in_the_shell_journal_fails_the_glass_step(monkeypatch, tmp_path, capsys):
    guest = _FakeGuest(shell_journal=["Extension fedora-glass-login@djshiye.github.io had error: boom"])
    lane = _lane(monkeypatch, tmp_path, guest)
    assert not lane.run(lb.plan())
    assert lane.results["glass"] == "FAIL" and "no error of the add-on" in lane.notes["glass"]
    assert "Extension fedora-glass-login@djshiye.github.io had error: boom" in capsys.readouterr().out
    # the steps that break the add-on on purpose do not look for errors
    assert lane.results["crash"] == "PASS" and lane.results["broken-addon"] == "PASS"
    assert not any('--since "@' in c and "_COMM=gnome-shell" in c for c in guest.cmds[-5:])


def test_a_clean_shell_journal_passes_and_is_read_in_the_judged_steps_only(monkeypatch, tmp_path):
    guest = _FakeGuest()
    lane = _lane(monkeypatch, tmp_path, guest)
    assert lane.run(lb.plan())
    reads = [c for c in guest.cmds if c.startswith('sudo journalctl -b _COMM=gnome-shell --since "@')]
    # glass, login (the prompt's place), restart (two boots), addon-update (before its login, and the prompt's place)
    assert len(reads) == 6


def test_gdm_retries_are_reported_in_the_note_and_the_closing_line_but_fail_nothing(monkeypatch, tmp_path, capsys):
    lane = _lane(monkeypatch, tmp_path, _FakeGuest(gdm_retries=2))
    assert lane.run(lb.plan())
    out = capsys.readouterr().out
    assert 'GDM said "Session never registered" 2 times in this step (glass on)' in out
    assert 'GDM said "Session never registered" 0 times in this step (glass on)' in out      # the other steps
    assert out.count("Session never registered, failing") == 2 and "greeter users seen: gdm-greeter-2" in out
    assert lane.notes["glass"] == "greeter retried 2×"
    table = lb.summary("ubuntu-26.04", lb.plan(), lane.results, lane.notes)
    assert "| 3. glass | PASS | greeter retried 2× |" in table
    assert lb.retry_summary(lane.retries) == 'GDM greeter retries ("Session never registered"): 2 in steps with the glass on, 0 with it off'


def test_retries_seen_with_the_glass_off_are_counted_as_off(monkeypatch, tmp_path):
    guest = _FakeGuest()
    lane = _lane(monkeypatch, tmp_path, guest)
    assert lane.run(["baseline", "on", "off"])
    guest.gdm_pending = 1
    lane.cur_step, lane.step_epoch = "off", 1
    lane.collect_gdm_retries()                              # the glass is off now
    assert lane.retries["off"]["off"] == 1 and "with it off" in lb.retry_summary(lane.retries)
    assert lb.retry_summary({}) == ""
