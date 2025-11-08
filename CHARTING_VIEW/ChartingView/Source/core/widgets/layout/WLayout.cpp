/*
  ==============================================================================

    WLayout.cpp
    Created: 8 Nov 2025 12:00:00am
    Author:  Jonathan

  ==============================================================================
*/

#include "WLayout.h"
#include "../ui/BaseComponent.h"

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
