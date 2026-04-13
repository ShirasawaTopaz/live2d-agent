"""Test that all skill modules can be imported."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_base_imports():
    """Test base skill module imports."""
    # Just test that the module can be imported
    import internal.skill as _  # noqa: F401

    print("[OK] Base imports successful")


def test_dynamic_loader_imports():
    """Test dynamic loader imports."""
    # Just test that the module can be imported
    import internal.skill.dynamic_loader as _  # noqa: F401

    print("[OK] Dynamic loader imports successful")


def test_class_instantiation():
    """Test that classes can be instantiated."""
    from internal.skill import SkillManager, DynamicSkillLoader

    # Create skill manager
    skill_manager = SkillManager(
        skill_dirs=["./skills"],
        prompt_manager=None,
        tool_registry=None,
    )

    # Create dynamic loader
    DynamicSkillLoader(
        skill_manager=skill_manager,
        use_polling=True,
    )

    print("[OK] Class instantiation successful")


if __name__ == "__main__":
    print("Testing skill module imports...\n")

    try:
        test_base_imports()
        test_dynamic_loader_imports()
        test_class_instantiation()
        print("\n[SUCCESS] All tests passed!")
    except Exception as e:
        print(f"\n[FAILED] Test failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
