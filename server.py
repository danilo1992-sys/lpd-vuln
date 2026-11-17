import os
import socket
import threading
import subprocess

VALID_QUEUE = os.environ.get("LPD_QUEUE", "cola")


def handle_client(sock):
    try:
        data = sock.recv(1024)

        if not data or data[0] != 2:
            return

        queue = data[1:].decode().strip()

        if queue != VALID_QUEUE:
            sock.sendall(b"\x01")
            return

        while True:
            header = sock.recv(1024)

            if not header:
                return

            sock.sendall(b"\x00")

            parts = header[1:].decode().split()

            if not parts:
                continue

            size = int(parts[0])

            if size > 1024 * 1024:
                return

            content = b""

            while len(content) < size:
                chunk = sock.recv(size - len(content))

                if not chunk:
                    return

                content += chunk

            job_name = "Unknown"

            for line in content.decode(errors="ignore").splitlines():
                if line.startswith("J"):
                    job_name = line[1:]
                    break

            # VULNERABLE
            subprocess.Popen(
                f"echo 'Archive: {job_name}' >> /tmp/archive.log", shell=True
            )

            sock.sendall(b"\x00")
            sock.sendall(b"\x00")

            return

    except Exception as e:
        print("Error:", e)

    finally:
        sock.close()


def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    server.bind(("0.0.0.0", 1515))
    server.listen(10)

    print("LPD vulnerable listening on 1515")

    while True:
        sock, addr = server.accept()

        threading.Thread(target=handle_client, args=(sock,), daemon=True).start()


if __name__ == "__main__":
    main()
