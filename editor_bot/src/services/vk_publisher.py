"""VK publisher stub. Inactive until VK account is unblocked."""

import structlog

log = structlog.get_logger()


class VKPublisher:
    """
    Placeholder for publishing to VK. Enable with VK_ENABLED=true and set VK_TOKEN, VK_GROUP_ID.
    Will be implemented after VK account is unblocked.
    """

    def __init__(self, token: str, group_id: str, enabled: bool = False) -> None:
        self.token = token
        self.group_id = group_id
        self.enabled = enabled

    async def publish_post(self, text: str, pdf_path: str | None = None) -> bool:
        """
        Publish text (and optionally PDF) to VK group. No-op when disabled.

        Args:
            text: Post text.
            pdf_path: Optional path to PDF (for future attachment).

        Returns:
            True if published, False if skipped or error.
        """
        if not self.enabled or not self.token or not self.group_id:
            log.info("vk_publish_skipped", reason="VK disabled or missing config")
            return False
        # TODO: implement VK API call when account is available
        log.info("vk_publish_stub", text_len=len(text))
        return False


async def publish_to_vk(text: str, pdf_path: str, vk_token: str, vk_group_id: str) -> bool:
    """
    Standalone helper for VK publication. Delegates to VKPublisher.

    Args:
        text: Post text.
        pdf_path: Path to PDF (for future attachment).
        vk_token: VK API token.
        vk_group_id: VK group ID.

    Returns:
        False (not implemented).
    """
    p = VKPublisher(vk_token, vk_group_id, enabled=bool(vk_token and vk_group_id))
    return await p.publish_post(text, pdf_path)
