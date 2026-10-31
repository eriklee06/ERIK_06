import http.server
import ipaddress
import os
import socket
import tkinter as tk
from tkinter import filedialog, messagebox
from urllib.parse import parse_qs, urlparse

PORT = 8765


def local_ipv4_addresses():
    found = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            address = info[4][0]
            if not address.startswith("127."):
                found.add(address)
    except OSError:
        pass
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("192.0.2.1", 80))
        found.add(sock.getsockname()[0])
        sock.close()
    except OSError:
        pass
    return sorted(found)


class Handler(http.server.BaseHTTPRequestHandler):
    destination = os.path.join(os.path.expanduser("~"), "Pictures", "LAN Photo Transfer")

    def log_message(self, fmt, *args):
        app.set_status(fmt % args)

    def do_GET(self):
        if urlparse(self.path).path != "/health":
            self.send_error(404)
            return
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"LAN Photo Transfer ready")

    def do_PUT(self):
        if urlparse(self.path).path != "/upload":
            self.send_error(404)
            return
        try:
            ip = ipaddress.ip_address(self.client_address[0])
            if not (ip.is_private or ip.is_loopback or ip.is_link_local):
                self.send_error(403, "Local network only")
                return
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 20 * 1024 * 1024 * 1024:
                self.send_error(413, "Invalid file size")
                return
            query = parse_qs(urlparse(self.path).query)
            filename = os.path.basename(query.get("filename", [""])[0]).strip()
            if not filename or filename in {".", ".."}:
                self.send_error(400, "Missing filename")
                return
            os.makedirs(self.destination, exist_ok=True)
            target = os.path.join(self.destination, filename)
            stem, ext = os.path.splitext(filename)
            suffix = 1
            while os.path.exists(target):
                target = os.path.join(self.destination, f"{stem} ({suffix}){ext}")
                suffix += 1
            remaining = length
            with open(target, "wb") as output:
                while remaining:
                    block = self.rfile.read(min(1024 * 1024, remaining))
                    if not block:
                        raise ConnectionError("Upload ended early")
                    output.write(block)
                    remaining -= len(block)
            self.send_response(201)
            self.end_headers()
            self.wfile.write(b"Saved")
            app.set_status(f"Saved {os.path.basename(target)}")
        except (ValueError, OSError, ConnectionError) as exc:
            app.set_status(f"Upload failed: {exc}")
            try:
                self.send_error(400, "Upload failed")
            except OSError:
                pass


class ReceiverApp:
    def __init__(self, root):
        self.root = root
        self.root.title("LAN Photo Transfer — Windows receiver")
        self.root.geometry("560x260")
        self.address = tk.StringVar(value="Finding laptop address…")
        self.folder = tk.StringVar(value=Handler.destination)
        self.status = tk.StringVar(value="Starting receiver…")
        tk.Label(root, text="Connect your iPhone to the same Wi-Fi", font=("Segoe UI", 14, "bold")).pack(pady=(18, 8))
        tk.Label(root, textvariable=self.address, font=("Consolas", 15)).pack(pady=4)
        tk.Label(root, text=f"Port {PORT}  •  enter this address in the iPhone app").pack()
        row = tk.Frame(root); row.pack(fill="x", padx=18, pady=16)
        tk.Entry(row, textvariable=self.folder).pack(side="left", fill="x", expand=True)
        tk.Button(row, text="Choose…", command=self.choose_folder).pack(side="left", padx=(8, 0))
        tk.Label(root, textvariable=self.status, wraplength=520).pack()
        self.refresh_addresses()

    def refresh_addresses(self):
        addresses = local_ipv4_addresses()
        self.address.set("   •   ".join(addresses) if addresses else "No Wi-Fi/LAN IPv4 address found")
        self.root.after(5000, self.refresh_addresses)

    def choose_folder(self):
        selected = filedialog.askdirectory(initialdir=self.folder.get())
        if selected:
            self.folder.set(selected)
            Handler.destination = selected

    def set_status(self, value):
        self.root.after(0, self.status.set, value)


app = None


def main():
    global app
    root = tk.Tk()
    app = ReceiverApp(root)
    server = http.server.ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    server.daemon_threads = True
    import threading
    threading.Thread(target=server.serve_forever, daemon=True).start()
    root.mainloop()
    server.shutdown()


if __name__ == "__main__":
    main()
