# kubectl — Kubernetes Command Reference

## Overview

`kubectl` is the command-line tool for interacting with Kubernetes clusters.

## Cluster Info

```bash
# Show cluster info
kubectl cluster-info

# Show node status
kubectl get nodes

# Show all namespaces
kubectl get namespaces
```

## Working with Pods

```bash
# List pods in default namespace
kubectl get pods

# List pods in all namespaces
kubectl get pods -A

# List pods with more detail
kubectl get pods -o wide

# Describe a pod (events, conditions, containers)
kubectl describe pod <pod-name>

# Get pod logs
kubectl logs <pod-name>

# Get logs from a specific container in a multi-container pod
kubectl logs <pod-name> -c <container-name>

# Follow logs in real-time
kubectl logs -f <pod-name>

# Get logs from the previous container instance (after crash)
kubectl logs <pod-name> --previous

# Execute a command in a running pod
kubectl exec -it <pod-name> -- /bin/bash

# Delete a pod
kubectl delete pod <pod-name>
```

## Deployments

```bash
# List deployments
kubectl get deployments

# Create a deployment
kubectl create deployment nginx --image=nginx:latest

# Scale a deployment
kubectl scale deployment nginx --replicas=3

# Update a deployment's image
kubectl set image deployment/nginx nginx=nginx:1.25

# Rollout status
kubectl rollout status deployment/nginx

# Rollback to previous version
kubectl rollout undo deployment/nginx

# View rollout history
kubectl rollout history deployment/nginx
```

## Services

```bash
# List services
kubectl get services

# Expose a deployment as a service
kubectl expose deployment nginx --port=80 --type=ClusterIP

# Create a NodePort service
kubectl expose deployment nginx --port=80 --type=NodePort

# Delete a service
kubectl delete service nginx
```

## Debugging

### Pod in CrashLoopBackOff

1. Check pod events: `kubectl describe pod <pod-name>`
2. Check logs: `kubectl logs <pod-name> --previous`
3. Check resource limits: pod may be OOM killed
4. Check liveness/readiness probes configuration
5. Try running the container image locally to reproduce

### Pod stuck in Pending

1. Check events: `kubectl describe pod <pod-name>`
2. Check node resources: `kubectl describe nodes | grep -A5 "Allocated resources"`
3. Check if PVC is bound: `kubectl get pvc`
4. Check node selectors/taints: `kubectl get nodes --show-labels`

### Pod stuck in ImagePullBackOff

1. Check image name and tag are correct
2. Check image pull secrets: `kubectl get secrets`
3. Try pulling the image manually on the node
4. Check network connectivity to the container registry

## Apply Manifests

```bash
# Apply a YAML manifest
kubectl apply -f deployment.yaml

# Apply all YAML files in a directory
kubectl apply -f ./manifests/

# Dry-run to see what would change
kubectl apply -f deployment.yaml --dry-run=client

# Delete resources defined in a manifest
kubectl delete -f deployment.yaml
```

## Context and Config

```bash
# Show current context
kubectl config current-context

# List all contexts
kubectl config get-contexts

# Switch context
kubectl config use-context <context-name>

# Set default namespace for current context
kubectl config set-context --current --namespace=<namespace>
```
