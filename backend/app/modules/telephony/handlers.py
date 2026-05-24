from app.core.config import config


async def register_handlers(ari, caller):

    @ari.on_stasis_start
    async def on_start(event):

        channel = event.channel

        if "UnicastRTP" in channel.name:
            return

        ctx = caller.ctx

        if ctx.active:
            return

        ctx.active = True
        ctx.channel_id = channel.id

        await channel.answer()

        ctx.bridge = await ari.ari.create_bridge(type="mixing")

        await ctx.bridge.add_channel(channel_id=channel.id)

        media = await ari.ari.create_external_media(
            external_host=f"{config.RTP_HOST}:{config.RTP_PORT}",
            format='ulaw'
        )
        vars = media.channelvars
        ctx.remote_addr = (
            vars["UNICASTRTP_LOCAL_ADDRESS"],
            int(vars["UNICASTRTP_LOCAL_PORT"])
        )
        await ctx.bridge.add_channel(channel_id=media.id)
        ctx.rtp_session.remote_addr = ctx.remote_addr
