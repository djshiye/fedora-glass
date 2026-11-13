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

def test_the_eleven_steps_in_order_with_removal_last():
    assert lb.plan() == ["baseline", "on", "glass", "login", "update", "restart", "off", "crash", "broken-addon",
                         "no-login", "removal"]
    for name, needs in lb.STEPS:
        for n in needs:
            assert lb.ORDER.index(n) < lb.ORDER.index(name), (name, n)
        assert hasattr(lb.Lane, "step_" + name.replace("-", "_")), name


def test_plan_adds_what_a_step_builds_on():
    assert lb.plan(["update"]) == ["baseline", "on", "glass", "login", "update"]
    assert lb.plan(["restart"]) == ["baseline", "on", "glass", "login", "update", "restart"]
    assert lb.plan(["removal", "crash"]) == ["baseline", "crash", "removal"]
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

    def __init__(self, guard_works=True, glass_draws=True, guard_too_eager=False):
        self.guard_works, self.glass_draws, self.guard_too_eager = guard_works, glass_draws, guard_too_eager
        self.boot, self.silent, self.cmds = "boot-1", 0, []
        self.state, self.token, self.stopped, self.values = "off", "", "", None
        self.note, self.glass, self.broken, self.removed = None, False, False, False
        self.logged_in, self.typed, self.boots, self.n = False, "", 0, 0
        self.family, self.gdm_unit = "fedora", "gdm.service"
        self.qmp = _FakeQmp(self)
        self.greeter_start()

    # the login screen
    def greeter_start(self):
        self.glass = False
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
                self.state = "on"
        elif keys == ["ret"]:
            self.typed = ""

    def type_text(self, text):
        self.typed += text

    def wake_screen(self):
        pass

    def picture(self, name):
        colour = bytes([230, 120, 60]) if self.glass else bytes([40, 40, 40])
        return lb.Picture(64, 40, colour * 64 * 40)

    def serial_tail(self, n=1):
        return "login: "

    def boot_id(self):
        return self.boot

    def reboot(self, label):
        self.logged_in = False
        self.boot = f"boot-{int(self.boot.split('-')[1]) + 1}"
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
        out = ""
        js = f"{lb.ADDON_DIR}/login.js"
        if cmd == f"{lb.HELPER} status":
            out = json.dumps({"version": 1, "available": True, "why": "", "state": self.state, "stopped": self.stopped,
                              "values": self.values, "picture_sha256": ""})
        elif cmd == f"systemctl show -p Result,ExecMainStatus {lb.GUARD}":
            out = "Result=success\nExecMainStatus=0"
        elif cmd == "sudo cat /var/lib/fedora-glass/login/state.json":
            out = json.dumps({"silent_boots": self.silent}) if self.state != "off" else ""
        elif cmd == "sudo cat /etc/fedora-glass/login/look.json":
            out = json.dumps({"version": 1, "token": self.token}) if self.state != "off" else ""
        elif cmd.startswith(f"sudo {lb.HELPER} on '"):
            values = json.loads(cmd.split("'")[1])
            if values.get("picture") == "wallpaper":
                assert input and input[:3] == b"\xff\xd8\xff"
            if self.state == "off":
                self.n += 1
                self.state, self.token, self.stopped, self.boots = "trial", f"{self.n:032x}", "", 0
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
        elif cmd.startswith("sudo sh -c 'printf"):
            assert "boot test" in cmd and js in cmd
            self.broken = True
        elif cmd.startswith("sudo cp -a /root/lgv-login.js.saved"):
            self.broken = False
        elif cmd.startswith("sudo dnf -y -q remove"):
            self.removed, self.state = True, "off"
        r = subprocess.CompletedProcess(cmd, 0, out.encode(), b"")
        r.out, r.err = out, ""
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
            if on:
                etc.append({"path": "db/gdm.d/50-fedora-glass", "kind": "f", "mode": "0o644", "owner": "0:0", "sha256": "x"})
            return {"gsettings": {"org.gnome.shell enabled-extensions": exts}, "dump": exts, "etc": etc}
        if args == ("denials",):
            return {"selinux": "Enforcing", "apparmor": "", "lines": []}
        if args == ("ours",):
            return {"dconf_files": ["/etc/dconf/db/gdm.d/50-fedora-glass"] if on else [], "etc_login": on}
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
    assert out.count("PASS step") == 11
    assert "silent_boots: 0" in out and out.count("the boot guard ran and succeeded") == 2
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
    assert {s: r for s, r in lane.results.items() if r != "PASS"} == {"restart": "FAIL"}
    assert "still on with nothing stopped" in lane.notes["restart"] and "'silent'" in lane.notes["restart"]
    assert f"systemd-analyze security {lb.GUARD} | tail -3" in guest.cmds
    assert f"sudo journalctl -b -u {lb.GUARD} --no-pager -n 200" in guest.cmds
    assert "----- BEGIN PNG fail-restart" in capsys.readouterr().out
