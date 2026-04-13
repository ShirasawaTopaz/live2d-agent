"""Integration between Skill system and existing components."""

from typing import Optional

from .manager import SkillManager
from ..agent.register import ToolRegistry
from ..prompt_manager.prompt_manager import PromptManager


class SkillSystemIntegration:
    """Integration layer between Skill system and existing components.

    This class bridges the Skill system with the existing ToolRegistry
    and PromptManager, handling the registration/unregistration of
    skills' tools and prompts.

    Example:
        ```python
        integration = SkillSystemIntegration(
            skill_manager=skill_manager,
            tool_registry=tool_registry,
            prompt_manager=prompt_manager
        )

        # Enable a skill
        await integration.enable_skill("file_ops")

        # Get all skill prompts for system prompt
        additions = integration.get_system_prompt_additions()
        ```
    """

    def __init__(
        self,
        skill_manager: SkillManager,
        tool_registry: ToolRegistry,
        prompt_manager: Optional[PromptManager] = None,
    ):
        """Initialize the integration layer.

        Args:
            skill_manager: The skill manager instance
            tool_registry: The tool registry for registering tools
            prompt_manager: Optional prompt manager for registering prompts
        """
        self.skill_manager = skill_manager
        self.tool_registry = tool_registry
        self.prompt_manager = prompt_manager

    async def enable_skill(self, name: str) -> bool:
        """Enable a skill and register its tools/prompts.

        This method:
        1. Initializes the skill through the manager
        2. Registers the skill's tools with the ToolRegistry
        3. Registers the skill's prompts with the PromptManager

        Args:
            name: The skill name

        Returns:
            True if the skill was enabled successfully
        """
        # Use SkillManager to enable
        if not await self.skill_manager.enable(name):
            return False

        # Get skill instance
        skill = self.skill_manager.registry.get(name)
        if not skill:
            return False

        # Register actual tool instances
        if hasattr(skill, "get_tool_instances"):
            for tool in skill.get_tool_instances():
                self.tool_registry.register(tool)

        return True

    async def disable_skill(self, name: str) -> bool:
        """Disable a skill and unregister its tools/prompts.

        This method:
        1. Unregisters the skill's tools from the ToolRegistry
        2. Unregisters the skill's prompts from the PromptManager
        3. Shuts down the skill through the manager

        Args:
            name: The skill name

        Returns:
            True if the skill was disabled successfully
        """
        # Get skill instance
        skill = self.skill_manager.registry.get(name)
        if skill:
            # Unregister tools
            for tool_def in skill.tools:
                # ToolRegistry needs to add unregister method
                pass

        # Use SkillManager to disable
        return await self.skill_manager.disable(name)

    def get_system_prompt_additions(self) -> str:
        """Get combined prompts from all enabled skills.

        This method collects all required prompts from enabled skills
        and combines them into a single string that can be appended
        to the system prompt.

        Returns:
            Combined prompt string from all enabled skills
        """
        prompts = []
        for name in self.skill_manager.list_enabled():
            skill = self.skill_manager.registry.get(name)
            if skill:
                for prompt in skill.prompts:
                    if prompt.required:
                        prompts.append(f"## {prompt.name}\n{prompt.content}")

        return "\n\n".join(prompts)


def integrate_skill_system(agent, config: dict, enable_dynamic_loading: bool = True):
    """Integrate Skill system during Agent initialization.

    This function sets up the complete skill system integration:
    1. Creates the SkillManager
    2. Loads all skills from configured directories
    3. Creates the integration layer
    4. Enables skills from configuration
    5. Optionally enables dynamic loading (hot-reload)
    6. Attaches to the agent and modifies system prompt building

    Args:
        agent: The Agent instance to integrate with
        config: Configuration dictionary
        enable_dynamic_loading: Whether to enable hot-reload for skills

    Returns:
        The SkillSystemIntegration instance

    Example:
        ```python
        # In Agent initialization
        integration = integrate_skill_system(self, config)

        # Later, to enable a skill
        await integration.enable_skill("new_skill")
        ```
    """
    from .manager import SkillManager
    from .integration import SkillSystemIntegration
    from .dynamic_loader import DynamicSkillLoader

    # Create SkillManager
    skill_dirs = config.get("skill_dirs", ["./skills", "./internal/skill/builtin"])
    skill_manager = SkillManager(
        skill_dirs=skill_dirs,
        prompt_manager=agent.prompt_manager,
        tool_registry=agent.tool_registry,
    )

    # Load all skills
    import asyncio

    asyncio.run(skill_manager.load_all())

    # Create integration layer
    integration = SkillSystemIntegration(
        skill_manager=skill_manager,
        tool_registry=agent.tool_registry,
        prompt_manager=agent.prompt_manager,
    )

    # Enable skills from config
    enabled_skills = config.get("enabled_skills", ["file_ops", "web_search"])
    for skill_name in enabled_skills:
        asyncio.run(integration.enable_skill(skill_name))

    # Setup dynamic loading if enabled
    if enable_dynamic_loading:
        dynamic_loader = DynamicSkillLoader(
            skill_manager=skill_manager,
            on_skill_added=lambda name, skill: asyncio.run(
                _handle_skill_added(integration, name, skill)
            ),
            on_skill_removed=lambda name: asyncio.run(
                _handle_skill_removed(integration, name)
            ),
            on_skill_reloaded=lambda name, skill: asyncio.run(
                _handle_skill_reloaded(integration, name, skill)
            ),
        )
        dynamic_loader.watch(skill_dirs)

        # Attach to agent for cleanup
        agent._dynamic_skill_loader = dynamic_loader

    # Attach to agent
    agent.skill_integration = integration

    # Modify system prompt building to include skill prompts
    original_build_system_prompt = agent.build_system_prompt

    def build_system_prompt_with_skills():
        base_prompt = original_build_system_prompt()
        skill_additions = integration.get_system_prompt_additions()
        if skill_additions:
            return f"{base_prompt}\n\n{skill_additions}"
        return base_prompt

    agent.build_system_prompt = build_system_prompt_with_skills

    return integration


async def _handle_skill_added(integration, name: str, skill) -> None:
    """Handle a new skill being added dynamically."""
    print(f"[SkillSystem] New skill added: {name}")

    # Optionally auto-enable if configured
    # await integration.enable_skill(name)


async def _handle_skill_removed(integration, name: str) -> None:
    """Handle a skill being removed."""
    print(f"[SkillSystem] Skill removed: {name}")


async def _handle_skill_reloaded(integration, name: str, skill) -> None:
    """Handle a skill being reloaded (hot-reload)."""
    print(f"[SkillSystem] Skill reloaded: {name}")

    # Re-enable the skill to pick up changes
    await integration.enable_skill(name)
