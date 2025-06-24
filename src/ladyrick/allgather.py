import os
import socket
import struct
import sys
import time


class AllGather:
    def __init__(self):
        if {"MASTER_ADDR", "MASTER_PORT", "WORLD_SIZE", "RANK"} - set(os.environ):
            raise RuntimeError("MASTER_ADDR, MASTER_PORT, WORLD_SIZE, RANK env is required")
        self.master_addr = os.environ["MASTER_ADDR"]
        self.master_port = int(os.environ["MASTER_PORT"])
        self.world_size = int(os.environ["WORLD_SIZE"])
        self.rank = int(os.environ["RANK"])
        assert 0 <= self.rank < self.world_size

    def allgather(self, data: bytes):
        if self.world_size == 1:
            assert self.rank == 0
            return [data]

        if self.rank == 0:
            gathered = self._run_master(data)
        else:
            gathered = self._run_worker(data)
        return gathered

    def _run_master(self, data: bytes):
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            server_socket.bind(("0.0.0.0", self.master_port))
            server_socket.listen(self.world_size - 1)
        except OSError as e:
            print(f"Master failed to bind port: {e}")
            sys.exit(1)

        try:
            # collect
            all_data = [data]
            conns: list[socket.socket] = []
            for worker_rank in range(1, self.world_size):
                conn, _ = server_socket.accept()
                conns.append(conn)
                cur_data_len = struct.unpack("!I", conn.recv(4))[0]
                cur_data = conn.recv(cur_data_len)
                all_data.append(cur_data)

            assert len(all_data) == self.world_size

            # broadcast
            data_len_pack = struct.pack("!" + "I" * len(all_data), *[len(d) for d in all_data])

            for worker_rank in range(1, self.world_size):
                conn = conns[worker_rank - 1]
                conn.sendall(data_len_pack)
                for d in all_data:
                    conn.sendall(d)
                conn.close()
        finally:
            server_socket.close()
        return all_data

    def _run_worker(self, data: bytes):
        worker_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        while True:
            try:
                worker_socket.connect((self.master_addr, self.master_port))
                break
            except (ConnectionRefusedError, socket.timeout):
                time.sleep(0.1)

        try:
            worker_socket.sendall(struct.pack("!I", len(data)))
            worker_socket.sendall(data)

            all_data: list[bytes] = []
            data_lens = struct.unpack("!" + "I" * self.world_size, worker_socket.recv(4 * self.world_size))
            for data_len in data_lens:
                all_data.append(worker_socket.recv(data_len))
        finally:
            worker_socket.close()
        return all_data


def main():
    import argparse

    parser = argparse.ArgumentParser(prog="allgather")
    parser.add_argument("msg", type=str, help="msg to allgather")
    parser.add_argument("-0", action="store_true", help="separate by \\0", dest="zero")

    args = parser.parse_args()

    allgather = AllGather()
    gathered = allgather.allgather(args.msg.encode())
    gathered_str = (s.decode() for s in gathered)
    if args.zero:
        print("\0".join(gathered_str), flush=True)
    else:
        print("\n".join(gathered_str), flush=True)


if __name__ == "__main__":
    main()
