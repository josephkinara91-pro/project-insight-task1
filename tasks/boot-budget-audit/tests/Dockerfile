FROM python:3.11-slim-bookworm@sha256:f06d01d4ba3f8ad5af45a3ec87df19c1d317d8e8961edc0fabda61811af6f7cf
RUN pip install --no-cache-dir z3-solver==4.13.3.0 pytest==9.1.1 pytest-json-ctrf==0.5.2
COPY . /tests/
RUN mkdir -p /app /logs/verifier \
    && cp /tests/public/netlist.py /app/netlist.py \
    && cp -R /tests/public/data /app/data \
    && chmod 755 /app \
    && chmod 700 /tests /logs/verifier
WORKDIR /tests
