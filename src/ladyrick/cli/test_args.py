import sys


def main():
    print(f"There are {len(sys.argv) - 1} args.", flush=True)
    for i, arg in enumerate(sys.argv[1:]):
        print(f"${i}: {arg}", flush=True)


if __name__ == "__main__":
    main()
