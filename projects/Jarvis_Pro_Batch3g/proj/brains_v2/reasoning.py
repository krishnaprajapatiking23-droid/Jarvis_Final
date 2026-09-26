def think(command, decision, plan):

    thoughts = []

    thoughts.append(f"User said: {command}")

    thoughts.append(f"Decision: {decision}")

    if plan:

        thoughts.append("Planning completed.")

        for step in plan:

            thoughts.append(f"• {step}")

    thoughts.append("Ready to execute.")

    return thoughts