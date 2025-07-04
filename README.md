# dler-discord

[DLer](https://github.com/lunae-f/dler)のAPIを利用して、Discord上から動画のダウンロードタスクを実行するためのBotです。

`/dler`コマンドを使って動画のURLを送信すると、`DLer`が動画のダウンロードを行い、完了後にダウンロードリンクを返信します。

## 主な機能

- スラッシュコマンド対応: `/dler {url}`で簡単にダウンロードタスクを開始できます。
- ステータス通知: タスクの作成、成功、失敗をDiscord上でリアルタイムに通知します。
- Docker対応: Docker Composeを使って簡単にBotを起動できます。

## 前提条件

このBotを動作させるには、以下の2つが必要です。

1. `DLer`の実行環境: このBotは`DLer`のAPIと通信します。事前に`DLer`がローカルまたはネットワーク上のどこかで稼働している必要があります。
2. Docker / Docker Compose: Botの実行環境として利用します。

## 導入と実行手順

### 1. Discord Botの準備

まず、Discord Developer PortalでBotを作成し、必要な情報を取得します。

1. Discord Developer Portalにアクセスし、新しいアプリケーションを作成します。
2. 作成したアプリケーションの「Bot」タブでMESSAGE CONTENT INTENTを有効にします。
3. 「Bot」タブで「Reset Token」をクリックし、BotのTokenをコピーしておきます。これは後で.envファイルに設定します。
4. 左側のメニューから「OAuth2」 > 「URL Generator」を開きます。
5. SCOPESでbotとapplications.commandsにチェックを入れます。
6. BOT PERMISSIONSでSend MessagesとEmbed Linksにチェックを入れます。
7. 生成されたURLにアクセスし、BotをあなたのDiscordサーバーに招待します。

### 2. サーバーの準備

1. このリポジトリをクローンします
```sh
git clone https://github.com/lunae-f/dler-discord
cd dler-discord
```
2. `.env`を編集します

### 3. サーバーの起動
```sh
docker compose up --build -d
```

### 4. 完了

Botがオンラインになったら、Discordのテキストチャンネルで`/dler`コマンドが利用可能になります。
以下のコマンドを送信して、ダウンロードリンクが返ってくれば成功です。
```
/dler url:{動画のURL}
```
