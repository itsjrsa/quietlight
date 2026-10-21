FROM node:25-bookworm-slim@sha256:81db02c4b671288a03915da9534dbd54f96d0e7c24d80ccc54f5b36b2e684370 AS assets
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
