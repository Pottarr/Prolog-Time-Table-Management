FROM swipl:latest

WORKDIR /app

COPY . .

EXPOSE 8080

CMD ["swipl", "-q", "-s", "main.pl", "-g", "start"]
