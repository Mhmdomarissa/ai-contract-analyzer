FROM node:20-bookworm-slim

WORKDIR /app

ENV PNPM_HOME=/usr/local/share/pnpm
ENV PATH=$PNPM_HOME:$PATH

RUN corepack enable

COPY . .

EXPOSE 3000

CMD ["pnpm", "dev"]
