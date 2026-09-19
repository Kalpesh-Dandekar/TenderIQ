import { TenderBlueprint, type BlueprintPageState } from "@/components/organization/blueprint/tender-blueprint";

export default async function TenderBlueprintPage({searchParams}:{searchParams:Promise<{state?:string;source?:string}>}) {
  const params=await searchParams;
  const state=params.state;
  const initialState:BlueprintPageState=state==="loading"||state==="processing"||state==="empty"||state==="error"?state:"available";
  return <TenderBlueprint initialState={params.source==="backend"?"loading":initialState} dataSource={params.source==="backend"?"backend":"preview"}/>;
}
