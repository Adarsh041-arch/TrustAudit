import os

from app.graph import build_graph
from app.state import AuditState


def main():
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("GOOGLE_API_KEY environment variable not set.")
        print("Set it with:  $env:GOOGLE_API_KEY = 'your-key-here'  (PowerShell)")
        return

    graph = build_graph()

    initial_state = AuditState(
        audit_title="Vendor Invoice Audit Q3 2026",
        uploaded_folder=r"C:\Users\adars\OneDrive\Desktop\AUDIT_AGENT\sample_docs",
    )

    result = graph.invoke(initial_state)

    report = result.get("final_report")
    if report:
        print(report.model_dump_json(indent=2))
    else:
        print("No report generated.")


if __name__ == "__main__":
    main()
