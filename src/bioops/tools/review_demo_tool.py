import subprocess


class ReviewDemoTool:
    """Small demo tool used only to test ReviewAgent patch review."""

    def run_step(self, sample_id: str) -> str:
        command = f"echo Processing sample {sample_id}"

        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            check=False,
        )

        return result.stdout.strip()
