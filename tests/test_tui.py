import asyncio
from cli.app import AgentTUI


async def test():
    app = AgentTUI()
    async with app.run_test(size=(120, 40)) as pilot:
        print("App started successfully!")
        chat = app.query_one("#chat-pane")
        tool = app.query_one("#tool-pane")
        inp = app.query_one("#input-box")
        print(f"Widgets: chat={chat.__class__.__name__}, tool={tool.__class__.__name__}, input={inp.__class__.__name__}")

        from cli.output import get_tui_queue
        q = get_tui_queue()
        print(f"Output queue set: {q is not None}")

        from cli.output import tui_print, OutputCategory
        tui_print("Hello from test", OutputCategory.INFO)
        await asyncio.sleep(0.2)
        print("ALL OK")


asyncio.run(test())
