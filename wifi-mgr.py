import sys
import solaros
from solaros import tui

WIFI_FILE = "/wifi_known.txt"


def load_known():
    known = {}
    try:
        with open(WIFI_FILE, "r") as f:
            for line in f:
                line = line.rstrip("\r\n")
                if not line or line.startswith("#"):
                    continue
                if "\t" in line:
                    ssid, pwd = line.split("\t", 1)
                elif ":" in line:
                    ssid, pwd = line.split(":", 1)
                else:
                    ssid, pwd = line, ""
                known[ssid] = pwd
    except OSError:
        pass
    return known


def save_known(known):
    try:
        with open(WIFI_FILE, "w") as f:
            for ssid, pwd in known.items():
                f.write(ssid + "\t" + pwd + "\n")
    except OSError:
        pass


def get_key_ch(key):
    if isinstance(key, str):
        return key
    if isinstance(key, int) and 32 <= key <= 126:
        return chr(key)
    return ""


def safe_wifi_start():
    try:
        solaros.wifi.start()
    except OSError:
        pass


def get_connected_ssid():
    try:
        st = solaros.wifi.status()
        if isinstance(st, dict):
            if st.get("connected") or st.get("state") in ("connected", "got_ip"):
                return st.get("ssid", "")
    except OSError:
        pass
    return ""


def connect_to_ap(ssid, pwd):
    current = get_connected_ssid()
    if current == ssid:
        return True, "Already connected: " + ssid

    try:
        solaros.wifi.disconnect()
    except OSError:
        pass

    try:
        if pwd:
            solaros.wifi.connect(ssid, pwd)
        else:
            solaros.wifi.connect(ssid)
        return True, "Connected to " + ssid
    except OSError as e:
        return False, "Error (" + ssid + "): " + str(e)


def do_scan(known, auto_connect=False):
    safe_wifi_start()
    try:
        raw = solaros.wifi.scan()
    except OSError as e:
        return [], "Scan error: " + str(e), False

    best = {}
    for ap in raw:
        ssid = ap.get("ssid", "")
        if not ssid:
            continue
        if ssid not in best or ap.get("rssi", -100) > best[ssid].get("rssi", -100):
            best[ssid] = ap

    aps = list(best.values())
    aps.sort(key=lambda x: x.get("rssi", -100), reverse=True)

    status_msg = "Found " + str(len(aps)) + " AP(s)."
    connected_ok = False

    if auto_connect and known:
        for ap in aps:
            ssid = ap.get("ssid", "")
            if ssid in known:
                ok, msg = connect_to_ap(ssid, known[ssid])
                status_msg = msg
                connected_ok = ok
                if ok:
                    break

    return aps, status_msg, connected_ok


def prompt_password(ssid):
    pwd = ""
    while not solaros.should_exit():
        rows, cols = tui.size()
        tui.clear()
        use_box = rows >= 8 and cols >= 20
        if use_box:
            tui.box(0, 0, rows, cols)
            pad_x = 2
            top_y = 1
        else:
            pad_x = 0
            top_y = 0

        avail_w = max(1, cols - (pad_x * 2))
        title = ("Add: " + ssid)[:avail_w]
        tui.addstr(top_y, pad_x, title, tui.BOLD)

        if rows >= 6:
            tui.addstr(top_y + 2, pad_x, "Password (blank=open):"[:avail_w])
            input_y = top_y + 3
        else:
            input_y = top_y + 1

        masked = "*" * len(pwd)
        disp_w = max(1, avail_w - 3)
        disp = masked[-disp_w:]
        tui.addstr(input_y, pad_x, "> " + disp + "_", tui.INVERSE)

        if rows >= 5:
            help_txt = "Enter:Save  Esc:Cancel" if cols >= 24 else "Ent:OK Esc:No"
            tui.addstr(rows - (2 if use_box else 1), pad_x, help_txt[:avail_w])

        tui.refresh()

        key = tui.getch(200)
        if key is None:
            continue
        if key == tui.KEY_ESCAPE:
            return None
        if key in (10, 13, "\n", "\r"):
            return pwd
        if key in (8, 127, "\b", "\x7f", tui.KEY_DELETE):
            pwd = pwd[:-1]
            continue
        ch = get_key_ch(key)
        if ch:
            pwd += ch
    return None


def main():
    auto_exit_mode = False
    for arg in sys.argv[1:]:
        if arg.lower() in ("auto", "--auto", "-a"):
            auto_exit_mode = True
            break

    known = load_known()
    selected = 0
    scroll = 0

    rows, cols = tui.size()
    tui.clear()
    tui.addstr(0, 0, "Scanning Wi-Fi..."[:max(1, cols)], tui.BOLD)
    tui.refresh()

    aps, status_msg, connected_ok = do_scan(known, auto_connect=True)

    if auto_exit_mode and connected_ok:
        tui.clear()
        tui.refresh()
        return

    while not solaros.should_exit():
        rows, cols = tui.size()
        tui.clear()

        use_box = rows >= 9 and cols >= 24
        if use_box:
            tui.box(0, 0, rows, cols)
            pad_x = 2
            header_y = 1
            list_top = 3
            footer_rows = 3
        else:
            pad_x = 0
            header_y = 0
            list_top = 1
            footer_rows = 2 if rows >= 5 else 1

        avail_w = max(1, cols - (pad_x * 2))

        try:
            w_stat = solaros.wifi.status_text()
        except OSError:
            w_stat = "unknown"

        header = ("Wi-Fi | " + w_stat) if cols >= 28 else w_stat
        tui.addstr(header_y, pad_x, header[:avail_w], tui.BOLD)
        if use_box:
            tui.hline(2, 1, cols - 2)

        list_height = max(1, rows - list_top - footer_rows)

        if not aps:
            tui.addstr(list_top, pad_x, "No APs. Press 's' to scan."[:avail_w])
        else:
            if selected >= len(aps):
                selected = len(aps) - 1
            if selected < 0:
                selected = 0
            if selected < scroll:
                scroll = selected
            elif selected >= scroll + list_height:
                scroll = selected - list_height + 1

            for idx in range(scroll, min(len(aps), scroll + list_height)):
                ap = aps[idx]
                ssid = ap.get("ssid", "<hidden>")
                rssi = str(ap.get("rssi", "?"))
                auth = str(ap.get("auth", ""))
                is_saved = ssid in known

                if cols >= 44:
                    tag = "[*]" if is_saved else "[ ]"
                    ssid_w = max(8, avail_w - 18)
                    line = "{} {:<{}} {:>4}dBm {}".format(tag, ssid[:ssid_w], ssid_w, rssi, auth[:6])
                elif cols >= 24:
                    tag = "*" if is_saved else " "
                    ssid_w = max(6, avail_w - 8)
                    line = "{}{:<{}} {:>4}".format(tag, ssid[:ssid_w], ssid_w, rssi)
                else:
                    tag = "*" if is_saved else " "
                    line = tag + ssid

                line = line[:avail_w]
                if len(line) < avail_w:
                    line = line + (" " * (avail_w - len(line)))

                attr = tui.INVERSE if idx == selected else tui.NORMAL
                tui.addstr(list_top + (idx - scroll), pad_x, line, attr)

        if use_box:
            tui.hline(rows - 3, 1, cols - 2)
            tui.addstr(rows - 2, pad_x, status_msg[:avail_w], tui.BOLD)
            help_line = "[Ent]Conn [s]Scan [a]Auto [d]Del [q]Quit" if cols >= 42 else "Ent:OK s:Scan a:Auto d:Del q:Quit"
            tui.addstr(rows - 1, pad_x, help_line[:avail_w])
        elif footer_rows >= 2:
            tui.addstr(rows - 2, pad_x, status_msg[:avail_w], tui.BOLD)
            tui.addstr(rows - 1, pad_x, "Ent:Conn s:Scan a:Auto d:Del q:Quit"[:avail_w])
        else:
            tui.addstr(rows - 1, pad_x, status_msg[:avail_w], tui.BOLD)

        tui.refresh()

        key = tui.getch(250)
        if key is None:
            continue

        ch = get_key_ch(key).lower()

        if key == tui.KEY_ESCAPE or ch == "q":
            break
        elif key == tui.KEY_UP:
            if selected > 0:
                selected -= 1
        elif key == tui.KEY_DOWN:
            if selected < len(aps) - 1:
                selected += 1
        elif key == tui.KEY_PAGE_UP:
            selected = max(0, selected - list_height)
        elif key == tui.KEY_PAGE_DOWN:
            selected = min(max(0, len(aps) - 1), selected + list_height)
        elif key == tui.KEY_HOME:
            selected = 0
        elif key == tui.KEY_END:
            selected = max(0, len(aps) - 1)
        elif ch == "s":
            status_msg = "Scanning..."
            tui.addstr(rows - (2 if (use_box or footer_rows >= 2) else 1), pad_x, status_msg[:avail_w], tui.BOLD)
            tui.refresh()
            aps, status_msg, _ = do_scan(known, auto_connect=False)
            selected = 0
            scroll = 0
        elif ch == "a":
            status_msg = "Auto-connecting..."
            tui.addstr(rows - (2 if (use_box or footer_rows >= 2) else 1), pad_x, status_msg[:avail_w], tui.BOLD)
            tui.refresh()
            aps, status_msg, _ = do_scan(known, auto_connect=True)
        elif ch == "d" and aps:
            ssid = aps[selected]["ssid"]
            if ssid in known:
                del known[ssid]
                save_known(known)
                try:
                    solaros.wifi.forget_ssid(ssid)
                except OSError:
                    pass
                status_msg = "Removed: " + ssid
            else:
                status_msg = "Not saved: " + ssid
        elif key in (10, 13, "\n", "\r") and aps:
            ssid = aps[selected]["ssid"]
            if ssid in known:
                pwd = known[ssid]
            else:
                pwd = prompt_password(ssid)
                if pwd is None:
                    status_msg = "Cancelled."
                    continue
                known[ssid] = pwd
                save_known(known)

            status_msg = "Connecting to " + ssid + "..."
            tui.addstr(rows - (2 if (use_box or footer_rows >= 2) else 1), pad_x, status_msg[:avail_w], tui.BOLD)
            tui.refresh()
            _, status_msg = connect_to_ap(ssid, pwd)


if __name__ == "__main__":
    main()
