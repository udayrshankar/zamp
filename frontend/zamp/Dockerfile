FROM node:22-alpine AS build

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# The numbered test invoices and their guide, plus a zip of them all.
FROM alpine:3.22 AS samples
RUN apk add --no-cache zip
WORKDIR /samples
COPY --from=iitm README.md ./
COPY --from=iitm correct/[0-9]*.pdf ./correct/
COPY --from=iitm incorrect/[0-9]*.pdf ./incorrect/
RUN zip -qr iitm-test-invoices.zip README.md correct incorrect

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
COPY --from=samples /samples /usr/share/nginx/html/samples
