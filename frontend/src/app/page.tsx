import { AgentIntelligence } from "@/components/landing/agent-intelligence";
import { BlueprintSpotlight } from "@/components/landing/blueprint-spotlight";
import { Capabilities } from "@/components/landing/capabilities";
import { EvidenceEvaluation } from "@/components/landing/evidence-evaluation";
import { Footer } from "@/components/landing/footer";
import { Hero } from "@/components/landing/hero";
import { Navbar } from "@/components/landing/navbar";
import { ProcurementSides } from "@/components/landing/procurement-sides";
import { ScaleSection } from "@/components/landing/scale-section";
import { Workflow } from "@/components/landing/workflow";

export default function Home() {
  return <div className="site-shell"><Navbar /><main><Hero /><Capabilities /><Workflow /><BlueprintSpotlight /><EvidenceEvaluation /><AgentIntelligence /><ScaleSection /><ProcurementSides /></main><Footer /></div>;
}
