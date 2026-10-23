FROM python:3.11-slim-bookworm@sha256:f06d01d4ba3f8ad5af45a3ec87df19c1d317d8e8961edc0fabda61811af6f7cf
RUN pip install --no-cache-dir z3-solver==4.13.3.0
WORKDIR /app
COPY netlist.py /app/netlist.py
COPY data /app/data
