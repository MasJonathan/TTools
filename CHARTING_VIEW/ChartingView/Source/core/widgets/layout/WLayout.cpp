/*
  ==============================================================================

    WLayout.cpp
    Created: 8 Nov 2025 12:00:00am
    Author:  Jonathan

  ==============================================================================
*/

#include "WLayout.h"
#include "../ui/BaseComponent.h"

void WParentLayout::applyLayout(const Rectangle<int>& bParent, const Array<Component*>& children) {
	const auto cs = getValidChildren(children);
	for (auto* c : cs) {
		const auto b = c->getLayout().LayoutBounds(bParent);
		c->setBounds(b);
	}
}

std::vector<BaseComponent*> WParentLayout::getValidChildren(const Array<Component*>& children) {
	std::vector<BaseComponent*> validChildren;

	for (auto* c : children) {
		if (auto* bc = dynamic_cast<BaseComponent*>(c)) {
			if (!bc->getPreferredSize().getIgnoreLayout()) {
				validChildren.push_back(bc);
			}
		}
	}

	return validChildren;
}
