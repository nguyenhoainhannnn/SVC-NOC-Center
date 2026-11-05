import { EndpointNode } from "./EndpointNode";
import { RouterNode } from "./RouterNode";
import { SwitchNode } from "./SwitchNode";
import { UnmanagedGroupNode } from "./UnmanagedGroupNode";

export const nocNodeTypes = {
  routerNode: RouterNode,
  switchNode: SwitchNode,
  unmanagedGroupNode: UnmanagedGroupNode,
  endpointNode: EndpointNode,
};

export * from "./types";
export * from "./layout";
export * from "./RemoteManageModal";
