
import os
from pathlib import Path

import aiohttp
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response


from bot.database.postgres import get_pg_connection


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

app = FastAPI(title="Bahor Market API")

# GitHub Pages do‘koniga API'dan foydalanishga ruxsat beramiz.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://marjona04123.github.io",
    ],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/")
def home():
    return {
        "message": "Bahor Market API ishlayapti!"
    }


@app.get("/api/products")
def get_products():
    connection = get_pg_connection()

    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT
                p.id,
                p.name,
                p.description,
                p.price,
                p.stock,
                p.image_file_id,
                c.name AS category_name
            FROM products AS p
            LEFT JOIN categories AS c
                ON c.id = p.category_id
            ORDER BY p.id DESC
            """
        )

        rows = cursor.fetchall()
        products = []

        for row in rows:
            products.append({
                "id": row["id"],
                "name": row["name"],
                "description": row["description"] or "",
                "price": row["price"],
                "category": row["category_name"] or "Boshqa",
                # Xaridorga aniq qoldiq sonini yubormaymiz.
                "available": row["stock"] > 0,
                "image_url": (
                    f"/api/products/{row['id']}/image"
                    if row["image_file_id"]
                    else None
                ),
            })

        return {"products": products}

    finally:
        connection.close()


@app.get("/api/products/{product_id}/image")
async def get_product_image(product_id: int):
    if not BOT_TOKEN:
        raise HTTPException(
            status_code=500,
            detail="Serverda BOT_TOKEN sozlanmagan."
        )

    connection = get_pg_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT image_file_id FROM products WHERE id = %s",
            (product_id,)
        )
        row = cursor.fetchone()
    finally:
        connection.close()

    if not row or not row["image_file_id"]:
        raise HTTPException(
            status_code=404,
            detail="Mahsulot rasmi topilmadi."
        )

    timeout = aiohttp.ClientTimeout(total=20)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        # Telegram'dan rasm faylining manzilini olamiz.
        telegram_api = (
            f"https://api.telegram.org/bot{BOT_TOKEN}/getFile"
        )

        async with session.get(
            telegram_api,
            params={"file_id": row["image_file_id"]}
        ) as response:
            result = await response.json()

        if not result.get("ok"):
            raise HTTPException(
                status_code=502,
                detail="Telegram'dan rasm manzilini olib bo‘lmadi."
            )

        file_path = result["result"]["file_path"]

        # Bot tokeni faqat backend ichida ishlatiladi.
        file_url = (
            f"https://api.telegram.org/file/bot"
            f"{BOT_TOKEN}/{file_path}"
        )

        async with session.get(file_url) as response:
            if response.status != 200:
                raise HTTPException(
                    status_code=502,
                    detail="Mahsulot rasmini yuklab bo‘lmadi."
                )

            image_bytes = await response.read()
            content_type = response.headers.get(
                "Content-Type",
                "image/jpeg"
            )

    if not content_type.startswith("image/"):
        content_type = "image/jpeg"

    return Response(
        content=image_bytes,
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=300"}
    )
