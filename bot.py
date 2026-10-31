import asyncio
import logging
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiohttp import web

from config import BOT_TOKEN, TAPO_DEVICES
from machines import MACHINE_IDS, format_status_line
from tapo_source import TapoSource

STATUS_SERVER_PORT = 8080
WEB_APP_PATH = Path(__file__).parent / "moydodyr-app.html"

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
tapo_source = TapoSource()


async def get_hybrid_statuses() -> dict[str, dict]:
    """Status for every machine: real Tapo reading for machines that have a
    plug configured in TAPO_DEVICES, "unknown" for the rest — no simulated
    data mixed in."""
    statuses = {mid: {"stage": "unknown", "remaining_seconds": None} for mid in MACHINE_IDS}
    if TAPO_DEVICES:
        statuses.update(await tapo_source.get_all_statuses())
    return statuses

# Temporary in-memory storage for "notify when free" subscriptions
# {user_id: {machine_id, ...}}
notify_subscriptions: dict[int, set[str]] = {}

# {machine_id: last known (non-"unknown") stage}, used to detect real
# busy->free transitions in poll_machines() below.
_last_notify_stage: dict[str, str] = {}

# Latest result of the background poll. /status, the web API and
# notifications all read this instead of polling the plugs themselves: the
# plugs' built-in HTTP servers fall over under many concurrent sessions
# (every open browser tab polling them every few seconds took both plugs
# offline), so poll_machines() is the only thing that talks to them.
latest_statuses: dict[str, dict] = {
    mid: {"stage": "unknown", "remaining_seconds": None} for mid in MACHINE_IDS
}

POLL_INTERVAL_SECONDS = 10


@dp.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "Hi! I keep track of the washing machines in the building.\n\n"
        "/status — status of all machines\n"
        "/notify — get notified when a machine frees up"
    )


@dp.message(Command("status"))
async def cmd_status(message: Message):
    lines = [format_status_line(mid, info) for mid, info in latest_statuses.items()]
    await message.answer("Machine status:\n\n" + "\n".join(lines))


@dp.message(Command("notify"))
async def cmd_notify(message: Message):
    builder = InlineKeyboardBuilder()
    for mid in MACHINE_IDS:
        builder.button(text=mid, callback_data=f"notify:{mid}")
    builder.adjust(4)
    await message.answer(
        "Which machine should I watch? I'll message you when it's free.",
        reply_markup=builder.as_markup(),
    )


@dp.callback_query(F.data.startswith("notify:"))
async def on_notify_pick(callback):
    machine_id = callback.data.split(":", 1)[1]
    user_id = callback.from_user.id
    notify_subscriptions.setdefault(user_id, set()).add(machine_id)
    await callback.answer()
    await callback.message.answer(
        f"Got it, I'll let you know when machine {machine_id} is free."
    )


async def poll_machines():
    """Background task, the only place that talks to the plugs: refreshes
    latest_statuses, then notifies subscribers when a machine goes from
    actually busy (washing/heating/spinning) to free. Never fires for
    "unknown" machines — no real data means no real event — and a brief
    "unknown" (network blip) doesn't hide a busy->free transition either."""
    global latest_statuses
    while True:
        statuses = await get_hybrid_statuses()
        latest_statuses = statuses

        for machine_id, info in statuses.items():
            stage = info["stage"]
            if stage == "unknown":
                continue
            was_busy = _last_notify_stage.get(machine_id) in ("washing", "heating", "spinning")
            _last_notify_stage[machine_id] = stage
            if not (was_busy and stage == "free"):
                continue

            for user_id, subscribed_ids in list(notify_subscriptions.items()):
                if machine_id in subscribed_ids:
                    try:
                        await bot.send_message(
                            user_id, f"🎉 Machine {machine_id} is free now!"
                        )
                    except Exception as e:
                        logging.warning(f"Failed to notify user {user_id}: {e}")
                    subscribed_ids.discard(machine_id)

        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def handle_status_api(request: web.Request) -> web.Response:
    return web.json_response(latest_statuses, headers={"Access-Control-Allow-Origin": "*"})


async def handle_web_app(request: web.Request) -> web.FileResponse:
    return web.FileResponse(WEB_APP_PATH)


async def start_status_server():
    """Serves moydodyr-app.html at / and the same statuses as /status at
    /api/status, so the page can be opened from another device via this
    server instead of only as a local file."""
    app = web.Application()
    app.router.add_get("/", handle_web_app)
    app.router.add_get("/api/status", handle_status_api)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", STATUS_SERVER_PORT)
    await site.start()
    logging.info(f"Status API listening on http://localhost:{STATUS_SERVER_PORT}/api/status")


async def main():
    asyncio.create_task(poll_machines())
    asyncio.create_task(start_status_server())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
