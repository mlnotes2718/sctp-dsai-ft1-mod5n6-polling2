# README

To run this code in render.com we need to create the following environment variables
```yml
TELEGRAM_BOT_TOKEN=
GROQ_API_KEY=
```

This app relies on the latest version of Telegram bot SDK. We can trigger to start a bot using polling method inside a flask app but since the latest SDK only support asynchronous. Our telegram bot app need to incorporate async command for the telegram related functions, however, flask is an synchronous app, therefore we need a lot of code to do bot management and thread management.

The simpler method is to use webhook.