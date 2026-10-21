FROM node:22-bookworm-slim@sha256:c3de60bf2f9dd0ac6370e6117950ff62d6e339527e7472301c9c78a017978392 AS assets
WORKDIR /build
COPY package*.json ./
RUN npm ci --ignore-scripts
COPY web ./web
RUN npm run build

FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258
WORKDIR /app
COPY server.py ./
COPY static ./static
COPY --from=assets /build/static/assets ./static/assets
RUN chmod -R a+rX /app
ENV PYTHONUNBUFFERED=1 RESEARCH_ROOT=/data PORT=8097
EXPOSE 8097
CMD ["python", "server.py"]
