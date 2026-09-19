import { TenderBlueprint, type BlueprintPageState } from "@/components/organization/blueprint/tender-blueprint";

export default async function TenderBlueprintPage({searchParams}:{searchParams:Promise<{state?:string}>}) {
  const state=(await searchParams).state;
  const initialState:BlueprintPageState=state==="loading"||state==="processing"||state==="empty"||state==="error"?state:"available";
  return <TenderBlueprint initialState={initialState}/>;
}
