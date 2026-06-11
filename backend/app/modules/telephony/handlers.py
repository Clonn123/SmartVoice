from app.core.config import config


async def register_handlers(ari, caller):

    @ari.on_stasis_start
    async def on_start(event):
        channel = event.channel

        if "UnicastRTP" in channel.name:
            return

        ctx = caller.ctx

        if ctx.active:
            print("STASIS START IGNORED: call already active")
            return

        ctx.active = True
        ctx.answered = True
        ctx.channel_id = channel.id

        try:
            await channel.answer()

            ctx.bridge = await ari.ari.create_bridge(type="mixing")

            await ctx.bridge.add_channel(channel_id=channel.id)

            media = await ari.ari.create_external_media(
                external_host=f"{config.RTP_HOST}:{config.RTP_PORT}",
                format="ulaw",
            )

            ctx.external_media_channel_id = media.id

            vars = media.channelvars

            ctx.remote_addr = (
                vars["UNICASTRTP_LOCAL_ADDRESS"],
                int(vars["UNICASTRTP_LOCAL_PORT"]),
            )

            await ctx.bridge.add_channel(channel_id=media.id)

            if ctx.rtp_session:
                ctx.rtp_session.remote_addr = ctx.remote_addr

            if caller.pipeline:
                caller.pipeline._queue_opening_greeting()

        except Exception as exc:
            print("STASIS START ERROR:", exc)

            try:
                if ctx.external_media_channel_id:
                    await ari.ari.delete_channel(ctx.external_media_channel_id)
            except Exception:
                pass

            try:
                if ctx.bridge:
                    await ctx.bridge.destroy()
            except Exception:
                pass

            caller.cleanup_call()

            raise

    @ari.on_stasis_end
    async def on_end(event):
        channel = event.channel
        ctx = caller.ctx

        if ctx.channel_id and ctx.channel_id != channel.id:
            return

        ctx.hangup_cause = getattr(event, "cause", None)
        ctx.hangup_text = getattr(event, "cause_txt", None)
        ctx.finished = True

        print(
            "📞 CALL FINISHED:",
            ctx.hangup_cause,
            ctx.hangup_text,
        )

        try:
            if ctx.external_media_channel_id:
                try:
                    await ari.ari.delete_channel(ctx.external_media_channel_id)
                except Exception:
                    pass

            if ctx.bridge:
                try:
                    await ctx.bridge.destroy()
                except Exception:
                    pass

        finally:
            # Оставляем конвейер и сессию RTP нетронутыми до тех пор, пока финализатор не соберет
            # артефакты диалогов и записи. Очистка произведет остановку позже.
            pass
