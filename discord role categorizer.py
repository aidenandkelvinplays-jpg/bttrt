import discord
from discord.ext import commands
from concurrent.futures import ThreadPoolExecutor
import asyncio
import threading

TOKEN = "MTUwNDYwNjEyMTEyMDUwMTg1MQ.G1ZiLH.POyl8QGJoodDcnUSF0vPIYqR0fjh7pdHOsQ7x0"

DIVIDER = "------------------------------"

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

bot = commands.Bot(
    command_prefix="?",
    intents=intents,
    help_command=None
)


# =========================
# Thread Manager System
# =========================
class ThreadManager:
    def __init__(self, max_workers=5):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.max_workers = max_workers
        self.semaphore = asyncio.Semaphore(max_workers)
        self.active_threads = 0
        self.lock = threading.Lock()
    
    async def _run_with_semaphore(self, coro):
        """Run a coroutine with semaphore limiting"""
        async with self.semaphore:
            return await coro
    
    async def run_async(self, coro):
        """Run an async function with worker limiting"""
        with self.lock:
            self.active_threads += 1
        try:
            return await self._run_with_semaphore(coro)
        finally:
            with self.lock:
                self.active_threads -= 1
    
    async def run_concurrent(self, tasks):
        """Run multiple async tasks concurrently with worker limiting"""
        with self.lock:
            self.active_threads += len(tasks)
        try:
            limited_tasks = [self._run_with_semaphore(task) for task in tasks]
            return await asyncio.gather(*limited_tasks)
        finally:
            with self.lock:
                self.active_threads -= len(tasks)
    
    def set_max_workers(self, new_max):
        """Change the number of worker threads"""
        self.max_workers = new_max
        self.executor._max_workers = new_max
        # Create new semaphore with new max_workers value
        self.semaphore = asyncio.Semaphore(new_max)
    
    def get_active_threads(self):
        """Get the number of active threads"""
        with self.lock:
            return self.active_threads
    
    def shutdown(self):
        """Shutdown the thread pool"""
        self.executor.shutdown(wait=True)


thread_manager = ThreadManager(max_workers=5)


# =========================
# help
# =========================
@bot.command()
async def help(ctx):

    await ctx.send(
        "**cmds**\n"
        "`?categorize <name>` - make category\n"
        "`?category_remover <name>` - delete category\n"
        "`?make_role <name>` - make role\n"
        "`?give_role <role> <@ppl>` - give role\n"
        "`?purge [1-100]` - delete messages\n"
        "`?threads` - set speed\n"
        "`?thread_speed` - test speed\n"
        "`?ping` - see latency\n"
        "`?logs` - set logs to a channel"
    )


# =========================
# categorize
# =========================
@bot.command()
@commands.has_permissions(manage_roles=True)
async def categorize(ctx, *, category_name):

    guild = ctx.guild
    bot_top_role = guild.me.top_role

    # Ask for category permissions
    await ctx.send(
        "**what perms?** (comma separated, or `none`)\n"
        "`administrator, manage_roles, manage_channels, manage_messages, kick_members, ban_members, display_role, mention_everyone`"
    )

    def check(message):
        return (
            message.author == ctx.author
            and message.channel == ctx.channel
        )

    try:
        perm_msg = await bot.wait_for(
            "message",
            check=check,
            timeout=60
        )
        perm_input = perm_msg.content.lower().strip()
    except:
        await ctx.send("timeout, no perms")
        perm_input = "none"

    # category role
    category_role = await guild.create_role(name=category_name)

    # Parse and apply permissions
    permissions = discord.Permissions()
    
    if perm_input != "none":
        perm_list = [p.strip() for p in perm_input.split(",")]
        
        perm_map = {
            "administrator": "administrator",
            "manage_roles": "manage_roles",
            "manage_channels": "manage_channels",
            "manage_messages": "manage_messages",
            "kick_members": "kick_members",
            "ban_members": "ban_members",
            "send_messages": "send_messages",
            "view_channel": "view_channel",
            "display_role": "display_role_separately",
            "mention_everyone": "mention_everyone"
        }
        
        for perm in perm_list:
            if perm in perm_map:
                permissions.update(**{perm_map[perm]: True})
    
    try:
        await category_role.edit(
            permissions=permissions,
            position=bot_top_role.position - 1
        )
    except:
        pass

    # top divider
    top_divider = await guild.create_role(
        name=DIVIDER
    )

    try:
        await top_divider.edit(
            position=category_role.position - 1
        )
    except:
        pass

    await ctx.send("alright, send me the role names (comma separated)")

    try:
        msg = await bot.wait_for(
            "message",
            check=check,
            timeout=120
        )
    except:
        await ctx.send("okay you're taking too long, nevermind")
        return

    role_names = [
        r.strip()
        for r in msg.content.split(",")
    ]

    current_position = top_divider.position - 1

    # create roles with threading
    async def create_role_async(role_name, position):
        loop = asyncio.get_event_loop()
        role = await guild.create_role(name=role_name)
        try:
            await role.edit(position=position)
        except:
            pass
        return role

    # Create all roles concurrently using thread manager
    tasks = []
    for i, role_name in enumerate(role_names):
        position = current_position - i
        tasks.append(create_role_async(role_name, position))

    await thread_manager.run_concurrent(tasks)

    # bottom divider
    bottom_divider = await guild.create_role(
        name=DIVIDER
    )

    try:
        await bottom_divider.edit(
            position=current_position - len(role_names)
        )
    except:
        pass

    # Ask if they want to assign roles to people
    await ctx.send("wanna give any of these roles to people? (yes/no)")

    try:
        assign_msg = await bot.wait_for(
            "message",
            check=check,
            timeout=60
        )
        if assign_msg.content.lower().strip() in ["yes", "y"]:
            await ctx.send("cool! format like this: `role_name: @person1 @person2`\nsend one per message, or type `done` when you're done")
            
            while True:
                try:
                    role_assign_msg = await bot.wait_for(
                        "message",
                        check=check,
                        timeout=60
                    )
                    
                    if role_assign_msg.content.lower().strip() == "done":
                        break
                    
                    if ":" not in role_assign_msg.content:
                        await ctx.send("oops, format should be `role_name: @person1 @person2`")
                        continue
                    
                    role_name_input, users_input = role_assign_msg.content.split(":", 1)
                    role_name_input = role_name_input.strip()
                    
                    role = discord.utils.get(guild.roles, name=role_name_input)
                    if not role:
                        await ctx.send(f"can't find role `{role_name_input}`")
                        continue
                    
                    mentions = role_assign_msg.mentions
                    if not mentions:
                        await ctx.send("i don't see anyone to give it to")
                        continue
                    
                    for user in mentions:
                        try:
                            await user.add_roles(role, category_role)
                        except:
                            pass
                    
                    await ctx.send(f"gave {len(mentions)} ppl the `{role_name_input}` role")
                except asyncio.TimeoutError:
                    await ctx.send("took too long")
                    break
    except asyncio.TimeoutError:
        pass

    await ctx.send("done")


# =========================
# remove category
# =========================
@bot.command()
@commands.has_permissions(manage_roles=True)
async def category_remover(ctx, *, category_name):

    guild = ctx.guild

    # lowest -> highest
    roles = sorted(
        guild.roles,
        key=lambda r: r.position
    )

    category_role = discord.utils.get(
        guild.roles,
        name=category_name
    )

    if not category_role:
        await ctx.send("cant find it")
        return

    category_index = roles.index(category_role)

    # divider below
    if category_index - 1 < 0:
        await ctx.send("broken category")
        return

    first_divider = roles[category_index - 1]

    if first_divider.name != DIVIDER:
        await ctx.send("divider missing")
        return

    roles_to_delete = [
        category_role,
        first_divider
    ]

    current_index = category_index - 2

    while current_index >= 0:

        role = roles[current_index]

        roles_to_delete.append(role)

        # bottom divider
        if role.name == DIVIDER:
            break

        current_index -= 1

    # delete roles with threading
    async def delete_role_async(role):
        try:
            await role.delete(reason="category removed")
            return True
        except:
            return False

    # Delete all roles concurrently using thread manager
    tasks = [delete_role_async(role) for role in roles_to_delete]
    results = await thread_manager.run_concurrent(tasks)
    
    deleted = sum(results)

    await ctx.send(f"deleted {deleted} roles")


# =========================
# make role
# =========================
@bot.command()
@commands.has_permissions(manage_roles=True)
async def make_role(ctx, *, role_name):

    guild = ctx.guild

    await ctx.send(
        "**what perms?** (comma separated, or `none`)\n"
        "`administrator, manage_roles, manage_channels, manage_messages, kick_members, ban_members, display_role, mention_everyone`"
    )

    def check(message):
        return (
            message.author == ctx.author
            and message.channel == ctx.channel
        )

    try:
        perm_msg = await bot.wait_for(
            "message",
            check=check,
            timeout=60
        )
        perm_input = perm_msg.content.lower().strip()
    except:
        await ctx.send("timeout, no perms")
        perm_input = "none"

    # Parse and apply permissions
    permissions = discord.Permissions()
    
    if perm_input != "none":
        perm_list = [p.strip() for p in perm_input.split(",")]
        
        perm_map = {
            "administrator": "administrator",
            "manage_roles": "manage_roles",
            "manage_channels": "manage_channels",
            "manage_messages": "manage_messages",
            "kick_members": "kick_members",
            "ban_members": "ban_members",
            "send_messages": "send_messages",
            "view_channel": "view_channel",
            "display_role": "display_role_separately",
            "mention_everyone": "mention_everyone"
        }
        
        for perm in perm_list:
            if perm in perm_map:
                permissions.update(**{perm_map[perm]: True})
    
    role = await guild.create_role(name=role_name, permissions=permissions)
    await ctx.send(f"created role `{role_name}`")


# =========================
# give role
# =========================
@bot.command()
@commands.has_permissions(manage_roles=True)
async def give_role(ctx, role_name: str, *, user_input):

    guild = ctx.guild
    
    role = discord.utils.get(guild.roles, name=role_name)
    
    if not role:
        await ctx.send(f"role `{role_name}` not found")
        return
    
    mentions = ctx.message.mentions
    
    if not mentions:
        await ctx.send("no users mentioned")
        return
    
    successful = 0
    
    for user in mentions:
        try:
            await user.add_roles(role)
            successful += 1
        except:
            pass
    
    await ctx.send(f"gave role to {successful}/{len(mentions)} ppl")


# =========================
# threads
# =========================
@bot.command()
async def threads(ctx, amount: int):


    if amount < 1 or amount > 1000:
        await ctx.send("use a number between 1-1000")
        return

    thread_manager.set_max_workers(amount)
    
    await ctx.send(f"set to {amount}")


# =========================
# thread_speed
# =========================
@bot.command()
async def thread_speed(ctx):

    ALLOWED_GUILD_ID = 1474591237628756048
    ALLOWED_ROLE_ID = 1504619900390473849

    if ctx.guild.id != ALLOWED_GUILD_ID:
        await ctx.send("nope")
        return

    user_role_ids = [role.id for role in ctx.author.roles]
    
    if ALLOWED_ROLE_ID not in user_role_ids:
        await ctx.send("nope")
        return

    await ctx.send("testing...")

    # Create test tasks
    async def dummy_task(duration=0.1):
        await asyncio.sleep(duration)
        return True

    # Test with 20 concurrent tasks
    import time
    start_time = time.time()
    
    tasks = [dummy_task() for _ in range(20)]
    await thread_manager.run_concurrent(tasks)
    
    elapsed_time = time.time() - start_time
    
    max_workers = thread_manager.max_workers
    tasks_per_second = 20 / elapsed_time
    
    await ctx.send(
        f"**results:**\n"
        f"workers: {max_workers}\n"
        f"time: {elapsed_time:.2f}s\n"
        f"tasks/sec: {tasks_per_second:.2f}"
    )

@bot.command()
@commands.has_permissions(manage_messages=True)
async def purge(ctx, amount: int):

    if amount < 1 or amount > 1000:
        await ctx.send("use 1-1000")
        return

    try:
        deleted = await ctx.channel.purge(limit=amount + 1)

        msg = await ctx.send(
            f"deleted {len(deleted) - 1} msgs"
        )

        await asyncio.sleep(3)
        await msg.delete()

    except Exception as e:
        await ctx.send(f"error: {e}")

# =========================
# spam (uses thread system)
# =========================
# =========================
# spam (uses thread system)
# =========================

log_channels = {}

@bot.command(name="logs")
async def logs(ctx, channel_id: int):
    """Set the log channel for deleted message logging"""
    try:
        channel = bot.get_channel(channel_id)
        if channel is None:
            await ctx.send(f"Could not find channel with ID {channel_id}")
            return
        
        log_channels[ctx.guild.id] = channel_id
        await ctx.send(f"Logging to {channel.mention}")
    except Exception as e:
        await ctx.send(f"Error: {str(e)}")

@bot.event
async def on_message_delete(message):
    """Triggered when a message is deleted"""
    if message.author.bot or not message.guild:
        return
    
    if message.guild.id not in log_channels:
        return
    
    log_channel = bot.get_channel(log_channels[message.guild.id])
    if log_channel is None:
        return
    
    log_text = f"# {message.author.name}\n\n* Deleted: {message.content}"
    await log_channel.send(log_text)

@bot.command()
async def ping(ctx):
    latency = round(bot.latency * 1000) 
    await ctx.send(f"{latency}ms")

@bot.command()
async def spam(ctx, amount: int, *, message_text):
    
    if amount < 1 or amount > 500:
        await ctx.send("use 1-500")
        return
    
    await ctx.send(f"sending {amount} messages...")
    
    import time
    start_time = time.time()
    
    async def send_message():
        try:
            await ctx.send(message_text)
        except:
            pass
    
    tasks = [send_message() for _ in range(amount)]
    await asyncio.gather(*tasks)
    
    elapsed_time = time.time() - start_time
    
    await ctx.send(f"sent {amount} in {elapsed_time:.2f}s ({amount/elapsed_time:.0f} msgs/sec)")


@spam.error
async def spam_error(ctx, error):
    pass

@categorize.error
async def categorize_error(ctx, error):

    if isinstance(
        error,
        commands.MissingPermissions
    ):
        await ctx.send("no perms")


@category_remover.error
async def category_remove_error(ctx, error):

    if isinstance(
        error,
        commands.MissingPermissions
    ):
        await ctx.send("no perms")


@make_role.error
async def make_role_error(ctx, error):

    if isinstance(
        error,
        commands.MissingPermissions
    ):
        await ctx.send("no perms")


@give_role.error
async def give_role_error(ctx, error):

    if isinstance(
        error,
        commands.MissingPermissions
    ):
        await ctx.send("no perms")


@purge.error
async def purge_error(ctx, error):
    pass


@threads.error
async def threads_error(ctx, error):
    pass


@thread_speed.error
async def thread_speed_error(ctx, error):
    pass


bot.run(TOKEN)