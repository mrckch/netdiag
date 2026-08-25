# iperf3-Gegenstelle für netdiag.
# Bewusst selbst gebaut statt Fremd-Image: ein Paket, kein Vertrauen in Dritte.
FROM alpine:3.22

RUN apk add --no-cache iperf3

# Server braucht keine Rechte; Port 5201 ist unprivilegiert.
USER nobody

EXPOSE 5201/tcp 5201/udp

ENTRYPOINT ["iperf3"]
CMD ["--server", "--port", "5201"]
