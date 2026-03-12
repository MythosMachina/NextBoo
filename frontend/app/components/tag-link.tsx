"use client";

import Link from "next/link";
import { MouseEvent, ReactNode } from "react";
import { useAuthState } from "./auth";
import { showTagContextMenu } from "./tag-context-menu";

type TagLinkProps = {
  href: string;
  tagName: string;
  className?: string;
  children: ReactNode;
};

export function TagLink({ href, tagName, className, children }: TagLinkProps) {
  const { authenticated } = useAuthState();

  function handleContextMenu(event: MouseEvent<HTMLAnchorElement>) {
    if (!authenticated) {
      return;
    }
    event.preventDefault();
    showTagContextMenu(event.clientX, event.clientY, tagName);
  }

  return (
    <Link className={className} href={href} onContextMenu={handleContextMenu}>
      {children}
    </Link>
  );
}
