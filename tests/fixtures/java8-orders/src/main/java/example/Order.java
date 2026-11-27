package example;

public final class Order {
    public static int total(int unitPrice, int quantity) {
        if (quantity < 0) throw new IllegalArgumentException("quantity must not be negative");
        return unitPrice * quantity;
    }
}
