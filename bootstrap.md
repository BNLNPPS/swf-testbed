# Bootstrap Guide for LLMs

**Attention AIs:** This is not a chronicle of completed work. This is quick essential background to current status and next steps.
Be concise and to the point. When something is done and isn't essential background for next steps, remove it.

**Repos** (siblings in /data/wenauseic/github/):
- **swf-testbed** - workflows, example agents
- **swf-monitor** - Django web app, REST API, MCP service
- **swf-common-lib** - BaseAgent class

**Host:** pandaserver02.sdcc.bnl.gov

## Current Status

**Preparing slides for talk.** Four main topics:
1. Fast processing workflow
2. Agent management
3. MCP integration
4. Multi-user support

**SVG Diagrams created in docs/images/:**
- `agent-management-overview-v*.svg` - Agent management with CLI/MCP/Claude relationships
- `multi-user-isolation-v*.svg` - Multi-user testbed with namespaces (wenauseic with torre1/torre2, zyang2)
- `architecture-panda-idds-v*.svg` - Overall architecture with PanDA/iDDS integration

## Next Steps

2. **Create second detailed iDDS/PanDA diagram** 

Human instruction for latest diagram updates:

We need to flesh out how the PanDA workload manager and the iDDS higher level workflow manager fit into the fast processing pipeline. 
- add an iDDS green box at 8 o'clock relative to DAQ Simulator
- it receives run imminent, run stop (ok the diagran doesn't cite the messages generally, but put them in here, this is a control channel complementing the data flow channel)
- two branches below iDDS:
one to Harvester which launches Pilots
one to PanDA which creates worker jobs
- the workers in the present diagram are the union of the two: jobs running inside pilots, so if you have the pilot and job boxes immediately to the left of the panda workers, you can have an arrow from mthem to panda workers
- this may be too complex for this present diagram, better have it in a second.
- in this diagram, just have iDDS flow to a PanDA box and that flows to point to the workers box.
Have a go at this update to the present diagram, and a second diagram that has more detail, the distinction between pilots launched by harvester and jobs created by panda, both under the direction of iDDS. Always use Harvester and PanDA in the diagrams.

The update of existing fast processing pipeline diagram is done. Create the second diagram.
